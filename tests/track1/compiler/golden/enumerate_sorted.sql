CREATE OR REPLACE PACKAGE ENUMERATE_SORTED AS
    PROCEDURE map_enumerate_sorted (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_enumerate_sorted_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END ENUMERATE_SORTED;
/

CREATE OR REPLACE PACKAGE BODY ENUMERATE_SORTED AS
    FUNCTION fn_enumerate_sorted_line_rule(p_idx IN NUMBER, p_itm IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_line_rule__dc JSON_OBJECT_T;
        v_val_line_rule__v0 NUMBER;
        v_val_line_rule__v1 VARCHAR2(4000 CHAR);
        v_val_line_rule__v2 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_line_rule__dc := JSON_OBJECT_T();
        v_val_line_rule__v0 := p_idx;
        IF v_val_line_rule__v0 IS NOT NULL THEN
            v_line_rule__dc.put('Position', v_val_line_rule__v0);
        END IF;
        v_val_line_rule__v1 := p_itm.get_String('id');
        IF v_val_line_rule__v1 IS NOT NULL THEN
            v_line_rule__dc.put('LineId', v_val_line_rule__v1);
        END IF;
        v_val_line_rule__v2 := p_itm.get_Number('price');
        IF v_val_line_rule__v2 IS NOT NULL THEN
            v_line_rule__dc.put('Price', v_val_line_rule__v2);
        END IF;
        RETURN v_line_rule__dc;
    END fn_enumerate_sorted_line_rule;

    PROCEDURE map_enumerate_sorted (
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
            IF v_forarr_0 IS NOT NULL THEN
                v_forarr_0 := TREAT(v_forarr_0.clone AS JSON_ARRAY_T);
                DECLARE
                    v_sortj_0 PLS_INTEGER;
                    v_sorttmp_0 JSON_ELEMENT_T;
                    v_sorttmpkey_0 JSON_ELEMENT_T;
                BEGIN
                    FOR v_sortk_0 IN 1 .. v_forarr_0.get_size - 1 LOOP
                        v_sorttmp_0 := v_forarr_0.get(v_sortk_0);
                        v_sorttmpkey_0 := TREAT(v_sorttmp_0 AS JSON_OBJECT_T).get('price');
                        v_sortj_0 := v_sortk_0 - 1;
                        WHILE v_sortj_0 >= 0 AND TREAT(v_forarr_0.get(v_sortj_0) AS JSON_OBJECT_T).get('price').compare_to(v_sorttmpkey_0) > 0 LOOP
                            v_forarr_0.put(v_sortj_0 + 1, v_forarr_0.get(v_sortj_0), TRUE);
                            v_sortj_0 := v_sortj_0 - 1;
                        END LOOP;
                        v_forarr_0.put(v_sortj_0 + 1, v_sorttmp_0, TRUE);
                    END LOOP;
                END;
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_itm JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    v_i NUMBER := v_i_0 + 1;
                    BEGIN
                        DECLARE
                            v_result_line_rule JSON_OBJECT_T;
                            v_omitted_line_rule BOOLEAN;
                        BEGIN
                            v_result_line_rule := fn_enumerate_sorted_line_rule(v_i, v_itm, v_omitted_line_rule);
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
                v_payload.put('mapping', 'enumerate_sorted');
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
                v_payload.put('mapping', 'enumerate_sorted');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        v_out_obj.put('Lines', v_arr_Lines);
        p_out := v_out_obj.TO_CLOB();
    END map_enumerate_sorted;

    PROCEDURE map_enumerate_sorted_safe (
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
            IF v_forarr_0 IS NOT NULL THEN
                v_forarr_0 := TREAT(v_forarr_0.clone AS JSON_ARRAY_T);
                DECLARE
                    v_sortj_0 PLS_INTEGER;
                    v_sorttmp_0 JSON_ELEMENT_T;
                    v_sorttmpkey_0 JSON_ELEMENT_T;
                BEGIN
                    FOR v_sortk_0 IN 1 .. v_forarr_0.get_size - 1 LOOP
                        v_sorttmp_0 := v_forarr_0.get(v_sortk_0);
                        v_sorttmpkey_0 := TREAT(v_sorttmp_0 AS JSON_OBJECT_T).get('price');
                        v_sortj_0 := v_sortk_0 - 1;
                        WHILE v_sortj_0 >= 0 AND TREAT(v_forarr_0.get(v_sortj_0) AS JSON_OBJECT_T).get('price').compare_to(v_sorttmpkey_0) > 0 LOOP
                            v_forarr_0.put(v_sortj_0 + 1, v_forarr_0.get(v_sortj_0), TRUE);
                            v_sortj_0 := v_sortj_0 - 1;
                        END LOOP;
                        v_forarr_0.put(v_sortj_0 + 1, v_sorttmp_0, TRUE);
                    END LOOP;
                END;
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_itm JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    v_i NUMBER := v_i_0 + 1;
                    BEGIN
                        DECLARE
                            v_result_line_rule JSON_OBJECT_T;
                            v_omitted_line_rule BOOLEAN;
                        BEGIN
                            v_result_line_rule := fn_enumerate_sorted_line_rule(v_i, v_itm, v_omitted_line_rule);
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
        v_out_obj.put('Lines', v_arr_Lines);
        p_out := v_out_obj.TO_CLOB();
    END map_enumerate_sorted_safe;
END ENUMERATE_SORTED;
/
