CREATE OR REPLACE FUNCTION fn_line_rule(p_itm IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
    v_line_rule__dc JSON_OBJECT_T;
BEGIN
    p_omitted := FALSE;
    v_line_rule__dc := JSON_OBJECT_T();
    v_line_rule__dc.put('LineId', p_itm.get_String('id'));
    v_line_rule__dc.put('LineAmount', p_itm.get_Number('price'));
    RETURN v_line_rule__dc;
END fn_line_rule;
/

CREATE OR REPLACE PROCEDURE map_lines_array (
    p_src IN  CLOB,
    p_out OUT CLOB
) AS
    v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
    v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
    TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
    v_errors   t_error_map;
    v_arr_Lines JSON_ARRAY_T := JSON_ARRAY_T();
BEGIN
    DECLARE
        v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
    BEGIN
        FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
            DECLARE
                v_itm JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
            BEGIN
                DECLARE
                    v_result_line_rule JSON_OBJECT_T;
                    v_omitted_line_rule BOOLEAN;
                BEGIN
                    v_result_line_rule := fn_line_rule(v_itm, v_omitted_line_rule);
                    IF NOT v_omitted_line_rule THEN
                        v_arr_Lines.append(v_result_line_rule);
                    END IF;
                EXCEPTION
                    WHEN OTHERS THEN
                        IF NOT v_errors.EXISTS('line_rule') THEN
                            v_errors('line_rule') := SQLERRM;
                        END IF;
                END;
            END;
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
            v_payload.put('mapping', 'lines_array');
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
            v_payload.put('mapping', 'lines_array');
            v_payload.put('total_errors', v_errors.COUNT);
            v_payload.put('shown', v_shown);
            v_payload.put('errors', v_err_arr);
            RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
        END;
    END IF;
    v_out_obj.put('Lines', v_arr_Lines);
    p_out := v_out_obj.TO_CLOB();
END map_lines_array;
/

CREATE OR REPLACE PROCEDURE map_lines_array_safe (
    p_src IN  CLOB,
    p_out OUT CLOB,
    p_err OUT CLOB
) AS
    v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
    v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
    TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
    v_errors   t_error_map;
    v_arr_Lines JSON_ARRAY_T := JSON_ARRAY_T();
BEGIN
    DECLARE
        v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
    BEGIN
        FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
            DECLARE
                v_itm JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
            BEGIN
                DECLARE
                    v_result_line_rule JSON_OBJECT_T;
                    v_omitted_line_rule BOOLEAN;
                BEGIN
                    v_result_line_rule := fn_line_rule(v_itm, v_omitted_line_rule);
                    IF NOT v_omitted_line_rule THEN
                        v_arr_Lines.append(v_result_line_rule);
                    END IF;
                EXCEPTION
                    WHEN OTHERS THEN
                        IF NOT v_errors.EXISTS('line_rule') THEN
                            v_errors('line_rule') := SQLERRM;
                        END IF;
                END;
            END;
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
END map_lines_array_safe;
/
