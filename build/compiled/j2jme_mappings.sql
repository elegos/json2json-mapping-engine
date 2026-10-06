CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAPPINGS AS
    PROCEDURE map_builtins_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_empty_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_empty_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_orders (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_orders_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    FUNCTION map_orders_fn (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE;

    PROCEDURE map_pick (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_pick_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_positions (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_positions_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_selection (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_selection_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_truthiness (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_truthiness_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAPPINGS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAPPINGS AS
    PROCEDURE map_builtins_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_TEXT.map_builtins_text(p_src, p_out);
    END map_builtins_text;

    PROCEDURE map_builtins_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_TEXT.map_builtins_text_safe(p_src, p_out, p_err);
    END map_builtins_text_safe;

    PROCEDURE map_empty_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_EMPTY_TEXT.map_empty_text(p_src, p_out);
    END map_empty_text;

    PROCEDURE map_empty_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_EMPTY_TEXT.map_empty_text_safe(p_src, p_out, p_err);
    END map_empty_text_safe;

    PROCEDURE map_orders (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_ORDERS.map_orders(p_src, p_out);
    END map_orders;

    PROCEDURE map_orders_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_ORDERS.map_orders_safe(p_src, p_out, p_err);
    END map_orders_safe;

    FUNCTION map_orders_fn (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE AS
    BEGIN
        RETURN MAPPING_OWNER.J2JME_MAP_ORDERS.map_orders_fn(p_src);
    END map_orders_fn;

    PROCEDURE map_pick (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_PICK.map_pick(p_src, p_out);
    END map_pick;

    PROCEDURE map_pick_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_PICK.map_pick_safe(p_src, p_out, p_err);
    END map_pick_safe;

    PROCEDURE map_positions (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_POSITIONS.map_positions(p_src, p_out);
    END map_positions;

    PROCEDURE map_positions_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_POSITIONS.map_positions_safe(p_src, p_out, p_err);
    END map_positions_safe;

    PROCEDURE map_selection (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_SELECTION.map_selection(p_src, p_out);
    END map_selection;

    PROCEDURE map_selection_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_SELECTION.map_selection_safe(p_src, p_out, p_err);
    END map_selection_safe;

    PROCEDURE map_truthiness (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_TRUTHINESS.map_truthiness(p_src, p_out);
    END map_truthiness;

    PROCEDURE map_truthiness_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_TRUTHINESS.map_truthiness_safe(p_src, p_out, p_err);
    END map_truthiness_safe;
END J2JME_MAPPINGS;
/
