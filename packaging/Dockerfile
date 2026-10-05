# The build image of the desktop packages: everything is built from Linux.
#   Linux    AppImage   Tauri's bundler
#   Windows  NSIS + zip cargo-xwin (MSVC target) + Tauri's NSIS bundler running on Linux
#   macOS    .app + dmg cargo-zigbuild (needs a macOS SDK, supplied at run time), rcodesign, libdmg-hfsplus
# Ubuntu 24.04: the AppImage runs on systems with at least this one's glibc (2.39), and it brings its own
# WebKitGTK: the 2.50 of Ubuntu 22.04 crashes on the COLRv1 emoji font (Noto) that current distributions have.
FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG NODE_MAJOR=22
ARG TAURI_CLI=2.12.0
ARG CARGO_XWIN=0.23.1
ARG APPLE_CODESIGN=0.29.0
ARG LIBDMG_COMMIT=6dfdec9ec335b1f04f366d96abc61388a3eb16d5

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential curl ca-certificates git pkg-config file xz-utils zip unzip cmake \
      libwebkit2gtk-4.1-dev libgtk-3-dev librsvg2-dev libssl-dev libayatana-appindicator3-dev libxdo-dev \
      patchelf wget \
      llvm lld clang scons g++ \
      xorriso zlib1g-dev libbz2-dev \
      python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Node, and Tauri's CLI as a prebuilt binary
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/* \
    && npm install -g @tauri-apps/cli@${TAURI_CLI}

# Rust: the host and the two cross targets; the tools are shared by every user of the image
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable \
    && rustup target add x86_64-pc-windows-msvc aarch64-apple-darwin \
    && chmod -R a+rX /opt/rustup /opt/cargo

# Windows: NSIS 3.13, the current one (Ubuntu 22.04 packages 3.08). The compiler (makensis) is built
# from the sources; the stubs, plugins and includes it needs come from the release for Windows,
# which are the same files whatever builds the compiler.
ARG NSIS=3.13
ARG NSIS_SRC_SHA256=a8ffe024602d46b6d766f9e1ce30c324ad2a24daeacd3efc2642d436a0c157ac
ARG NSIS_ZIP_SHA256=ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8
RUN cd /tmp \
    && curl -fsSL -o nsis-src.tar.bz2 https://sourceforge.net/projects/nsis/files/NSIS%203/${NSIS}/nsis-${NSIS}-src.tar.bz2/download \
    && curl -fsSL -o nsis.zip https://sourceforge.net/projects/nsis/files/NSIS%203/${NSIS}/nsis-${NSIS}.zip/download \
    && echo "$NSIS_SRC_SHA256  nsis-src.tar.bz2" | sha256sum -c - && echo "$NSIS_ZIP_SHA256  nsis.zip" | sha256sum -c - \
    && unzip -q nsis.zip && mv nsis-${NSIS} /opt/nsis \
    && tar -xjf nsis-src.tar.bz2 && cd nsis-${NSIS}-src \
    && scons -j"$(nproc)" SKIPSTUBS=all SKIPPLUGINS=all SKIPUTILS=all SKIPMISC=all \
         VERSION=${NSIS} NSIS_CONFIG_CONST_DATA_PATH=no PREFIX=/tmp/nsis-built install-compiler \
    && install -m755 "$(find /tmp/nsis-built -name makensis -type f | head -1)" /opt/nsis/makensis \
    && printf '#!/bin/sh\nexec env NSISDIR=/opt/nsis /opt/nsis/makensis "$@"\n' > /usr/local/bin/makensis \
    && chmod +x /usr/local/bin/makensis && rm -rf /tmp/nsis*

# Windows: cargo-xwin downloads the MSVC CRT and the Windows SDK at the first build
RUN cd /tmp && f=cargo-xwin-v${CARGO_XWIN}.x86_64-unknown-linux-musl.tar.gz \
    && curl -fsSLO https://github.com/rust-cross/cargo-xwin/releases/download/v${CARGO_XWIN}/$f \
    && curl -fsSLO https://github.com/rust-cross/cargo-xwin/releases/download/v${CARGO_XWIN}/$f.sha256 \
    && sha256sum -c $f.sha256 && tar -xzf $f -C /usr/local/bin && rm -f $f $f.sha256

# macOS: zig links, rcodesign signs, libdmg-hfsplus makes the dmg
RUN pip3 install --no-cache-dir --break-system-packages cargo-zigbuild
RUN cd /tmp && f=apple-codesign-${APPLE_CODESIGN}-x86_64-unknown-linux-musl.tar.gz \
    && curl -fsSLO https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign%2F${APPLE_CODESIGN}/$f \
    && curl -fsSLO https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign%2F${APPLE_CODESIGN}/$f.sha256 \
    && echo "$(cut -d' ' -f1 $f.sha256)  $f" | sha256sum -c - \
    && tar -xzf $f && install -m755 apple-codesign-${APPLE_CODESIGN}-x86_64-unknown-linux-musl/rcodesign /usr/local/bin/rcodesign \
    && rm -rf /tmp/apple-codesign-*
RUN git clone https://github.com/theuni/libdmg-hfsplus /tmp/libdmg && cd /tmp/libdmg \
    && git checkout ${LIBDMG_COMMIT} && cmake -B build -DCMAKE_BUILD_TYPE=Release . \
    && cmake --build build -j"$(nproc)" \
    && install -m755 "$(find build -name dmg -type f -perm -u+x | head -1)" /usr/local/bin/dmg \
    && rm -rf /tmp/libdmg

# uv, for the Python side of the staging (dependencies as wheels of the target platform)
RUN curl -fsSL https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

# Tauri's AppImage bundler runs linuxdeploy and its appimage plugin, which are AppImages themselves.
# There is no FUSE in a container, and a host with binfmt_misc handlers for AppImage (AppImageLauncher)
# runs them through a program that does not exist in here. Tauri deals with linuxdeploy itself (it blanks the
# AppImage marker); its plugin, which linuxdeploy starts, is unpacked now and replaced by a script.
ENV XDG_CACHE_HOME=/opt/cache APPIMAGE_EXTRACT_AND_RUN=1 NO_STRIP=1
COPY unpack-appimage.sh /usr/local/bin/unpack-appimage
RUN apt-get update && apt-get install -y --no-install-recommends squashfs-tools && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/cache/tauri /opt/appimages && cd /opt/cache/tauri \
    && curl -fsSLO https://github.com/tauri-apps/binary-releases/releases/download/apprun-old/AppRun-x86_64 \
    && curl -fsSLO https://github.com/tauri-apps/binary-releases/releases/download/linuxdeploy-07333c6/linuxdeploy-x86_64.AppImage \
    && mv linuxdeploy-x86_64.AppImage linuxdeploy-07333c6-x86_64.AppImage && chmod +x linuxdeploy-07333c6-x86_64.AppImage \
    && curl -fsSLO https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage \
    && mv linuxdeploy-plugin-appimage-x86_64.AppImage linuxdeploy-plugin-appimage.AppImage \
    && unpack-appimage linuxdeploy-plugin-appimage.AppImage /opt/appimages/plugin-appimage \
    && chmod -R a+rwX /opt/cache /opt/appimages
WORKDIR /work
