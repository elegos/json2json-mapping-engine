CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAPPINGS AS
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
END J2JME_MAPPINGS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAPPINGS AS
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
END J2JME_MAPPINGS;
/
