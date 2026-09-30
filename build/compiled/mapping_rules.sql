CREATE OR REPLACE PACKAGE MAPPING_OWNER.MAPPING_FUNCTIONS AS
    FUNCTION fn_orders_unit_price(p_src IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER;

    FUNCTION fn_orders_order_id(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2;

    FUNCTION fn_orders_line(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T;
END MAPPING_FUNCTIONS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.MAPPING_FUNCTIONS AS
    FUNCTION fn_orders_unit_price(p_src IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN (p_src.get_Number('total') / p_src.get_Number('qty'));
    END fn_orders_unit_price;

    FUNCTION fn_orders_order_id(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN p_root.get_String('id');
    END fn_orders_order_id;

    FUNCTION fn_orders_line(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_line__dc JSON_OBJECT_T;
        v_line__rc0 NUMBER;
        v_line__ro0 BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_line__dc := JSON_OBJECT_T();
        v_line__dc.put('Sku', p_src.get_String('sku'));
        v_line__dc.put('Qty', p_src.get_Number('qty'));
        BEGIN
            v_line__rc0 := MAPPING_FUNCTIONS.fn_orders_unit_price(p_src, v_line__ro0);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT p__errors.has('unit_price') THEN
                    p__errors.put('unit_price', SQLERRM);
                END IF;
                v_line__ro0 := TRUE;
        END;
        IF NOT v_line__ro0 THEN
            v_line__dc.put('Unit', v_line__rc0);
        END IF;
        RETURN v_line__dc;
    END fn_orders_line;
END MAPPING_FUNCTIONS;
/

CREATE OR REPLACE PACKAGE MAPPING_OWNER.MAPPING_RULES AS
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
END MAPPING_RULES;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.MAPPING_RULES AS
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
            v_result_order_id := MAPPING_FUNCTIONS.fn_orders_order_id(v_srcroot, v_omitted_order_id);
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
            v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
        BEGIN
            FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                DECLARE
                    v_src JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                BEGIN
                    DECLARE
                        v_result_line JSON_OBJECT_T;
                        v_omitted_line BOOLEAN;
                    BEGIN
                        v_result_line := MAPPING_FUNCTIONS.fn_orders_line(v_srcroot, v_src, v_rule_errors, v_omitted_line);
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
            v_result_order_id := MAPPING_FUNCTIONS.fn_orders_order_id(v_srcroot, v_omitted_order_id);
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
            v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
        BEGIN
            FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                DECLARE
                    v_src JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                BEGIN
                    DECLARE
                        v_result_line JSON_OBJECT_T;
                        v_omitted_line BOOLEAN;
                    BEGIN
                        v_result_line := MAPPING_FUNCTIONS.fn_orders_line(v_srcroot, v_src, v_rule_errors, v_omitted_line);
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
END MAPPING_RULES;
/
