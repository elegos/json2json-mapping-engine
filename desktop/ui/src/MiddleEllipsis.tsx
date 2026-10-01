import { useLayoutEffect, useRef, useState } from "react";

/** `text` with the middle cut out (`/home/gfu…ders-test`) so that it fits the width it is given:
 * as many characters on the left as on the right, none cut when it already fits. */
export function fitMiddle(text: string, fits: (candidate: string) => boolean): string {
  if (fits(text)) return text;
  const shown = (k: number) => `${text.slice(0, k)}…${text.slice(text.length - k)}`;
  let low = 0;
  let high = Math.floor(text.length / 2);
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (fits(shown(mid))) low = mid;
    else high = mid - 1;
  }
  return shown(low);
}

export function MiddleEllipsis({ text, className }: { text: string; className?: string }) {
  const box = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(text);

  useLayoutEffect(() => {
    const element = box.current;
    if (!element) return;
    const canvas = document.createElement("canvas").getContext("2d");
    const measure = () => {
      if (!canvas) return setShown(text);
      const style = getComputedStyle(element);
      canvas.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      const room = element.clientWidth;
      setShown(fitMiddle(text, (candidate) => canvas.measureText(candidate).width <= room));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text]);

  return (
    <span ref={box} className={className} title={text}>
      {shown}
    </span>
  );
}
