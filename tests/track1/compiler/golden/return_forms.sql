CREATE OR REPLACE PROCEDURE map_return_forms (
    p_src IN  CLOB,
    p_out OUT CLOB
) AS
    v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
    v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
    TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
    v_errors   t_error_map;
    e_field_omitted EXCEPTION;

        FUNCTION fn_status_label RETURN VARCHAR2 IS
        BEGIN
            IF (v_srcroot.get_String('status') = 'ACTIVE') THEN
                RETURN 'Active';
            ELSIF (v_srcroot.get_String('status') = 'CANCELLED') THEN
                RETURN NULL;
            ELSE
                RAISE e_field_omitted;
            END IF;
        END fn_status_label;

        FUNCTION fn_risky_amount RETURN NUMBER IS
        BEGIN
            RETURN (v_srcroot.get_Number('amount') / v_srcroot.get_Number('divisor'));
        END fn_risky_amount;
BEGIN
    BEGIN
        v_out_obj.put('StatusLabel', fn_status_label());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('status_label') THEN
                v_errors('status_label') := SQLERRM;
            END IF;
    END;

    BEGIN
        v_out_obj.put('RiskyAmount', fn_risky_amount());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('risky_amount') THEN
                v_errors('risky_amount') := SQLERRM;
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
            v_payload.put('mapping', 'return_forms');
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
            v_payload.put('mapping', 'return_forms');
            v_payload.put('total_errors', v_errors.COUNT);
            v_payload.put('shown', v_shown);
            v_payload.put('errors', v_err_arr);
            RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
        END;
    END IF;
    p_out := v_out_obj.TO_CLOB();
END map_return_forms;
/

CREATE OR REPLACE PROCEDURE map_return_forms_safe (
    p_src IN  CLOB,
    p_out OUT CLOB,
    p_err OUT CLOB
) AS
    v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
    v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
    TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
    v_errors   t_error_map;
    e_field_omitted EXCEPTION;

        FUNCTION fn_status_label RETURN VARCHAR2 IS
        BEGIN
            IF (v_srcroot.get_String('status') = 'ACTIVE') THEN
                RETURN 'Active';
            ELSIF (v_srcroot.get_String('status') = 'CANCELLED') THEN
                RETURN NULL;
            ELSE
                RAISE e_field_omitted;
            END IF;
        END fn_status_label;

        FUNCTION fn_risky_amount RETURN NUMBER IS
        BEGIN
            RETURN (v_srcroot.get_Number('amount') / v_srcroot.get_Number('divisor'));
        END fn_risky_amount;
BEGIN
    BEGIN
        v_out_obj.put('StatusLabel', fn_status_label());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('status_label') THEN
                v_errors('status_label') := SQLERRM;
            END IF;
    END;

    BEGIN
        v_out_obj.put('RiskyAmount', fn_risky_amount());
    EXCEPTION
        WHEN e_field_omitted THEN
            NULL;
        WHEN OTHERS THEN
            IF NOT v_errors.EXISTS('risky_amount') THEN
                v_errors('risky_amount') := SQLERRM;
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
END map_return_forms_safe;
/
