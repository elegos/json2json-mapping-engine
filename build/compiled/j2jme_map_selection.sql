CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_SELECTION AS
    PROCEDURE map_selection (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_selection_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_SELECTION;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_SELECTION AS
    FUNCTION fn_selection_a(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN p_root.get_String('id');
    END fn_selection_a;

    FUNCTION fn_selection_my_object(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_my_object__dc JSON_OBJECT_T;
    BEGIN
        p_omitted := FALSE;
        v_my_object__dc := JSON_OBJECT_T();
        v_my_object__dc.put('Id', MAPPING_OWNER.J2JME_FUNCTIONS.split_first(p_src.get_String('remarks'), '|'));
        v_my_object__dc.put('Name', p_src.get_String('name'));
        RETURN v_my_object__dc;
    END fn_selection_my_object;

    FUNCTION fn_selection_my_object_first(p_root IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_my_object_first_matches JSON_ARRAY_T;
        v_forarr_0 JSON_ARRAY_T;
        v_my_object_first_item JSON_OBJECT_T;
        v_my_object_first__rc0 JSON_OBJECT_T;
        v_my_object_first__ro0 BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_my_object_first_matches := JSON_ARRAY_T();
        v_forarr_0 := p_root.get_Array('myList');
        FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
            v_my_object_first_item := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
            IF ((v_my_object_first_item.get_String('discriminator') = 'MY D') AND (v_my_object_first_item.get_String('other') = p_root.get_String('rootElement'))) THEN
                BEGIN
                    v_my_object_first__rc0 := fn_selection_my_object(p_root, v_my_object_first_item, v_my_object_first__ro0);
                EXCEPTION
                    WHEN OTHERS THEN
                        IF NOT p__errors.has('my_object') THEN
                            p__errors.put('my_object', SQLERRM);
                        END IF;
                        v_my_object_first__ro0 := TRUE;
                END;
                IF NOT v_my_object_first__ro0 THEN
                    v_my_object_first_matches.append(v_my_object_first__rc0);
                END IF;
            END IF;
        END LOOP;
        IF (v_my_object_first_matches IS NOT NULL AND v_my_object_first_matches.get_size > 0) THEN
            RETURN v_my_object_first_matches.get_Object(0);
        END IF;
        p_omitted := TRUE;
        RETURN NULL;
    END fn_selection_my_object_first;

    PROCEDURE map_selection (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
    BEGIN
        DECLARE
            v_result_a VARCHAR2(4000 CHAR);
            v_omitted_a BOOLEAN;
        BEGIN
            v_result_a := fn_selection_a(v_srcroot, v_omitted_a);
            IF NOT v_omitted_a THEN
                v_out_obj.put('A', v_result_a);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('a') THEN
                    v_errors('a') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_my_object_first JSON_OBJECT_T;
            v_omitted_my_object_first BOOLEAN;
        BEGIN
            v_result_my_object_first := fn_selection_my_object_first(v_srcroot, v_rule_errors, v_omitted_my_object_first);
            IF NOT v_omitted_my_object_first THEN
                v_out_obj.put('MyObject', v_result_my_object_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('my_object_first') THEN
                    v_errors('my_object_first') := SQLERRM;
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
                v_payload.put('mapping', 'selection');
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
                v_payload.put('mapping', 'selection');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_selection;

    PROCEDURE map_selection_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
    BEGIN
        DECLARE
            v_result_a VARCHAR2(4000 CHAR);
            v_omitted_a BOOLEAN;
        BEGIN
            v_result_a := fn_selection_a(v_srcroot, v_omitted_a);
            IF NOT v_omitted_a THEN
                v_out_obj.put('A', v_result_a);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('a') THEN
                    v_errors('a') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_my_object_first JSON_OBJECT_T;
            v_omitted_my_object_first BOOLEAN;
        BEGIN
            v_result_my_object_first := fn_selection_my_object_first(v_srcroot, v_rule_errors, v_omitted_my_object_first);
            IF NOT v_omitted_my_object_first THEN
                v_out_obj.put('MyObject', v_result_my_object_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('my_object_first') THEN
                    v_errors('my_object_first') := SQLERRM;
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
        p_out := v_out_obj.TO_CLOB();
    END map_selection_safe;
END J2JME_MAP_SELECTION;
/
