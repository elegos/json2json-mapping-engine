CREATE OR REPLACE PACKAGE SIMPLE_OBJECT AS
    PROCEDURE map_simple_object (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_simple_object_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END SIMPLE_OBJECT;
/

CREATE OR REPLACE PACKAGE BODY SIMPLE_OBJECT AS
    FUNCTION fn_simple_object_order_id(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN p_root.get_String('id');
    END fn_simple_object_order_id;

    FUNCTION fn_simple_object_amount(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN (p_root.get_Number('price') * p_root.get_Number('qty'));
    END fn_simple_object_amount;

    FUNCTION fn_simple_object_discount_code(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(p_root.get_String('discountCode'), 'NONE');
    END fn_simple_object_discount_code;

    PROCEDURE map_simple_object (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_order_id VARCHAR2(4000 CHAR);
            v_omitted_order_id BOOLEAN;
        BEGIN
            v_result_order_id := fn_simple_object_order_id(v_srcroot, v_omitted_order_id);
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
            v_result_amount NUMBER;
            v_omitted_amount BOOLEAN;
        BEGIN
            v_result_amount := fn_simple_object_amount(v_srcroot, v_omitted_amount);
            IF NOT v_omitted_amount THEN
                v_out_obj.put('Amount', v_result_amount);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('amount') THEN
                    v_errors('amount') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_discount_code VARCHAR2(4000 CHAR);
            v_omitted_discount_code BOOLEAN;
        BEGIN
            v_result_discount_code := fn_simple_object_discount_code(v_srcroot, v_omitted_discount_code);
            IF NOT v_omitted_discount_code THEN
                v_out_obj.put('DiscountCode', v_result_discount_code);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('discount_code') THEN
                    v_errors('discount_code') := SQLERRM;
                END IF;
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
                v_payload.put('mapping', 'simple_object');
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
                v_payload.put('mapping', 'simple_object');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_simple_object;

    PROCEDURE map_simple_object_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_order_id VARCHAR2(4000 CHAR);
            v_omitted_order_id BOOLEAN;
        BEGIN
            v_result_order_id := fn_simple_object_order_id(v_srcroot, v_omitted_order_id);
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
            v_result_amount NUMBER;
            v_omitted_amount BOOLEAN;
        BEGIN
            v_result_amount := fn_simple_object_amount(v_srcroot, v_omitted_amount);
            IF NOT v_omitted_amount THEN
                v_out_obj.put('Amount', v_result_amount);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('amount') THEN
                    v_errors('amount') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_discount_code VARCHAR2(4000 CHAR);
            v_omitted_discount_code BOOLEAN;
        BEGIN
            v_result_discount_code := fn_simple_object_discount_code(v_srcroot, v_omitted_discount_code);
            IF NOT v_omitted_discount_code THEN
                v_out_obj.put('DiscountCode', v_result_discount_code);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('discount_code') THEN
                    v_errors('discount_code') := SQLERRM;
                END IF;
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
        p_out := v_out_obj.TO_CLOB();
    END map_simple_object_safe;
END SIMPLE_OBJECT;
/
