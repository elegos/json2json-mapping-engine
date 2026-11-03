CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_ORDERS AS
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
END J2JME_MAP_ORDERS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_ORDERS AS
    FUNCTION fn_orders_unit_price(p_src IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_unit_price__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_unit_price__ret := (p_src.get_Number('total') / p_src.get_Number('qty'));
        IF v_unit_price__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_unit_price__ret;
    END fn_orders_unit_price;

    FUNCTION fn_orders_order_id(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_order_id__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_order_id__ret := p_root.get_String('id');
        IF v_order_id__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_order_id__ret;
    END fn_orders_order_id;

    FUNCTION fn_orders_line(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_line__dc JSON_OBJECT_T;
        v_val_line__v0 VARCHAR2(4000 CHAR);
        v_val_line__v1 NUMBER;
        v_val_line__v2 VARCHAR2(4000 CHAR);
        v_line__rc3 NUMBER;
        v_line__ro3 BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_line__dc := JSON_OBJECT_T();
        v_val_line__v0 := p_src.get_String('sku');
        IF v_val_line__v0 IS NOT NULL THEN
            v_line__dc.put('Sku', v_val_line__v0);
        END IF;
        v_val_line__v1 := p_src.get_Number('qty');
        IF v_val_line__v1 IS NOT NULL THEN
            v_line__dc.put('Qty', v_val_line__v1);
        END IF;
        v_val_line__v2 := MAPPING_OWNER.J2JME_FUNCTIONS.split_first(p_src.get_String('sku'), '-');
        IF v_val_line__v2 IS NOT NULL THEN
            v_line__dc.put('Family', v_val_line__v2);
        END IF;
        BEGIN
            v_line__rc3 := fn_orders_unit_price(p_src, v_line__ro3);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT p__errors.has('unit_price') THEN
                    p__errors.put('unit_price', SQLERRM);
                END IF;
                v_line__ro3 := TRUE;
        END;
        IF NOT v_line__ro3 THEN
            v_line__dc.put('Unit', v_line__rc3);
        END IF;
        RETURN v_line__dc;
    END fn_orders_line;

    FUNCTION fn_orders_currency(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_currency__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_currency__ret := MAPPING_OWNER.J2JME_FUNCTIONS.lookup(p_root.get_String('country'), p_root.get_Object('currencies'), 'N/A');
        IF v_currency__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_currency__ret;
    END fn_orders_currency;

    FUNCTION fn_orders_warehouse(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_warehouse__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_warehouse__ret := MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('ref'), ',', 2);
        IF v_warehouse__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_warehouse__ret;
    END fn_orders_warehouse;

    PROCEDURE map_orders (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
        v_arr_Lines JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_result_order_id VARCHAR2(4000 CHAR);
            v_omitted_order_id BOOLEAN;
        BEGIN
            v_result_order_id := fn_orders_order_id(v_srcroot, v_omitted_order_id);
            IF NOT v_omitted_order_id THEN
                v_out_obj.put('OrderId', v_result_order_id);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('order_id') THEN
                    v_errors('order_id') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_currency VARCHAR2(4000 CHAR);
            v_omitted_currency BOOLEAN;
        BEGIN
            v_result_currency := fn_orders_currency(v_srcroot, v_omitted_currency);
            IF NOT v_omitted_currency THEN
                v_out_obj.put('Currency', v_result_currency);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('currency') THEN
                    v_errors('currency') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_warehouse VARCHAR2(4000 CHAR);
            v_omitted_warehouse BOOLEAN;
        BEGIN
            v_result_warehouse := fn_orders_warehouse(v_srcroot, v_omitted_warehouse);
            IF NOT v_omitted_warehouse THEN
                v_out_obj.put('Warehouse', v_result_warehouse);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('warehouse') THEN
                    v_errors('warehouse') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
        BEGIN
            IF v_forarr_0 IS NOT NULL THEN
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_src JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_line JSON_OBJECT_T;
                            v_omitted_line BOOLEAN;
                        BEGIN
                            v_result_line := fn_orders_line(v_srcroot, v_src, v_rule_errors, v_omitted_line);
                            IF NOT v_omitted_line THEN
                                v_arr_Lines.append(v_result_line);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('line') THEN
                                    v_errors('line') := SQLERRM;
                                END IF;
                        END;
                    END;
                END LOOP;
            END IF;
        END;

        DECLARE
            v_rule_keys JSON_KEY_LIST := v_rule_errors.get_keys;
        BEGIN
            FOR v_k IN 1 .. v_rule_keys.COUNT LOOP
                IF NOT v_errors.EXISTS(v_rule_keys(v_k)) THEN
                    v_errors(v_rule_keys(v_k)) := v_rule_errors.get_String(v_rule_keys(v_k));
                END IF;
            END LOOP;
        END;
        IF v_errors.COUNT > 0 THEN
            DECLARE
                v_err_arr   JSON_ARRAY_T := JSON_ARRAY_T();
                v_err_obj   JSON_OBJECT_T;
                v_key       VARCHAR2(200);
                v_shown     PLS_INTEGER := 0;
                v_payload   JSON_OBJECT_T := JSON_OBJECT_T();
                v_base_len  PLS_INTEGER;
                v_running_len PLS_INTEGER;
            BEGIN
                v_payload.put('mapping', 'orders');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', 0);
                v_payload.put('errors', v_err_arr);
                v_base_len := LENGTHB(v_payload.to_string());
                v_running_len := v_base_len;
                v_key := v_errors.FIRST;
                WHILE v_key IS NOT NULL AND v_shown < 20 LOOP
                    v_err_obj := JSON_OBJECT_T();
                    v_err_obj.put('rule', v_key);
                    v_err_obj.put('cause', v_errors(v_key));
                    EXIT WHEN v_running_len + LENGTHB(v_err_obj.to_string()) + 1 > 1800;
                    v_err_arr.append(v_err_obj);
                    v_running_len := v_running_len + LENGTHB(v_err_obj.to_string()) + 1;
                    v_shown := v_shown + 1;
                    v_key := v_errors.NEXT(v_key);
                END LOOP;
                v_payload := JSON_OBJECT_T();
                v_payload.put('mapping', 'orders');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        v_out_obj.put('Lines', v_arr_Lines);
        p_out := v_out_obj.TO_CLOB();
    END map_orders;

    PROCEDURE map_orders_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
        v_arr_Lines JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_result_order_id VARCHAR2(4000 CHAR);
            v_omitted_order_id BOOLEAN;
        BEGIN
            v_result_order_id := fn_orders_order_id(v_srcroot, v_omitted_order_id);
            IF NOT v_omitted_order_id THEN
                v_out_obj.put('OrderId', v_result_order_id);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('order_id') THEN
                    v_errors('order_id') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_currency VARCHAR2(4000 CHAR);
            v_omitted_currency BOOLEAN;
        BEGIN
            v_result_currency := fn_orders_currency(v_srcroot, v_omitted_currency);
            IF NOT v_omitted_currency THEN
                v_out_obj.put('Currency', v_result_currency);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('currency') THEN
                    v_errors('currency') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_warehouse VARCHAR2(4000 CHAR);
            v_omitted_warehouse BOOLEAN;
        BEGIN
            v_result_warehouse := fn_orders_warehouse(v_srcroot, v_omitted_warehouse);
            IF NOT v_omitted_warehouse THEN
                v_out_obj.put('Warehouse', v_result_warehouse);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('warehouse') THEN
                    v_errors('warehouse') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
        BEGIN
            IF v_forarr_0 IS NOT NULL THEN
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_src JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_line JSON_OBJECT_T;
                            v_omitted_line BOOLEAN;
                        BEGIN
                            v_result_line := fn_orders_line(v_srcroot, v_src, v_rule_errors, v_omitted_line);
                            IF NOT v_omitted_line THEN
                                v_arr_Lines.append(v_result_line);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('line') THEN
                                    v_errors('line') := SQLERRM;
                                END IF;
                        END;
                    END;
                END LOOP;
            END IF;
        END;

        DECLARE
            v_rule_keys JSON_KEY_LIST := v_rule_errors.get_keys;
        BEGIN
            FOR v_k IN 1 .. v_rule_keys.COUNT LOOP
                IF NOT v_errors.EXISTS(v_rule_keys(v_k)) THEN
                    v_errors(v_rule_keys(v_k)) := v_rule_errors.get_String(v_rule_keys(v_k));
                END IF;
            END LOOP;
        END;
        DECLARE
            v_err_arr JSON_ARRAY_T := JSON_ARRAY_T();
            v_err_obj JSON_OBJECT_T;
            v_key     VARCHAR2(200);
        BEGIN
            v_key := v_errors.FIRST;
            WHILE v_key IS NOT NULL LOOP
                v_err_obj := JSON_OBJECT_T();
                v_err_obj.put('rule', v_key);
                v_err_obj.put('cause', v_errors(v_key));
                v_err_arr.append(v_err_obj);
                v_key := v_errors.NEXT(v_key);
            END LOOP;
            p_err := v_err_arr.to_clob();
        END;
        v_out_obj.put('Lines', v_arr_Lines);
        p_out := v_out_obj.TO_CLOB();
    END map_orders_safe;

    -- @parallel declared by: line (degree=2).
    -- The degree is chosen by the caller, e.g.
    --   SELECT /*+ PARALLEL(2) */ map_orders_fn(doc) FROM staging
    FUNCTION map_orders_fn (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE AS
        v_out CLOB;
    BEGIN
        map_orders(p_src, v_out);
        RETURN v_out;
    END map_orders_fn;
END J2JME_MAP_ORDERS;
/
