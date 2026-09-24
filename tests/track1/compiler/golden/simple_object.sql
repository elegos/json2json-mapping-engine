CREATE OR REPLACE PROCEDURE map_simple_object (
    p_src IN  CLOB,
    p_out OUT CLOB
) AS
    v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
    v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
    TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
    v_errors   t_error_map;
    e_field_omitted EXCEPTION;

        FUNCTION fn_order_id RETURN VARCHAR2 IS
        BEGIN
            RETURN v_srcroot.get_String('id');
        END fn_order_id;

        FUNCTION fn_amount RETURN NUMBER IS
        BEGIN
            RETURN (v_srcroot.get_Number('price') * v_srcroot.get_Number('qty'));
        END fn_amount;

        FUNCTION fn_discount_code RETURN VARCHAR2 IS
        BEGIN
            RETURN COALESCE(v_srcroot.get_String('discountCode'), 'NONE');
        END fn_discount_code;
BEGIN
    BEGIN
        v_out_obj.put('OrderId', fn_order_id());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('order_id') THEN
                v_errors('order_id') := SQLERRM;
            END IF;
    END;

    BEGIN
        v_out_obj.put('Amount', fn_amount());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('amount') THEN
                v_errors('amount') := SQLERRM;
            END IF;
    END;

    BEGIN
        v_out_obj.put('DiscountCode', fn_discount_code());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
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
/

CREATE OR REPLACE PROCEDURE map_simple_object_safe (
    p_src IN  CLOB,
    p_out OUT CLOB,
    p_err OUT CLOB
) AS
    v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
    v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
    TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
    v_errors   t_error_map;
    e_field_omitted EXCEPTION;

        FUNCTION fn_order_id RETURN VARCHAR2 IS
        BEGIN
            RETURN v_srcroot.get_String('id');
        END fn_order_id;

        FUNCTION fn_amount RETURN NUMBER IS
        BEGIN
            RETURN (v_srcroot.get_Number('price') * v_srcroot.get_Number('qty'));
        END fn_amount;

        FUNCTION fn_discount_code RETURN VARCHAR2 IS
        BEGIN
            RETURN COALESCE(v_srcroot.get_String('discountCode'), 'NONE');
        END fn_discount_code;
BEGIN
    BEGIN
        v_out_obj.put('OrderId', fn_order_id());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('order_id') THEN
                v_errors('order_id') := SQLERRM;
            END IF;
    END;

    BEGIN
        v_out_obj.put('Amount', fn_amount());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('amount') THEN
                v_errors('amount') := SQLERRM;
            END IF;
    END;

    BEGIN
        v_out_obj.put('DiscountCode', fn_discount_code());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
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
/
