CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_KEYWORD_FIELDS AS
    PROCEDURE map_keyword_fields (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_keyword_fields_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_KEYWORD_FIELDS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_KEYWORD_FIELDS AS
    FUNCTION fn_keyword_fields_number(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_number__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_number__ret := p_root.get_Object('return').get_String('number');
        IF v_number__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_number__ret;
    END fn_keyword_fields_number;

    FUNCTION fn_keyword_fields_from_a(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_from_a__agg NUMBER;
        v_aggarr_0 JSON_ARRAY_T;
        v_aggel_0 JSON_OBJECT_T;
        v_aggn_0 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_0 := p_root.get_Object('return').get_Array('items');
        v_aggn_0 := 0;
        IF v_aggarr_0 IS NOT NULL THEN
            FOR v_aggk_0 IN 0 .. v_aggarr_0.get_size - 1 LOOP
                v_aggel_0 := TREAT(v_aggarr_0.get(v_aggk_0) AS JSON_OBJECT_T);
                IF (v_aggel_0.get_String('from') = 'A') THEN
                    v_aggn_0 := v_aggn_0 + 1;
                END IF;
            END LOOP;
        END IF;
        v_from_a__agg := v_aggn_0;
        IF v_from_a__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_from_a__agg;
    END fn_keyword_fields_from_a;

    PROCEDURE map_keyword_fields (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_number VARCHAR2(4000 CHAR);
            v_omitted_number BOOLEAN;
        BEGIN
            v_result_number := fn_keyword_fields_number(v_srcroot, v_omitted_number);
            IF NOT v_omitted_number THEN
                v_out_obj.put('Number', v_result_number);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number') THEN
                    v_errors('number') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_from_a NUMBER;
            v_omitted_from_a BOOLEAN;
        BEGIN
            v_result_from_a := fn_keyword_fields_from_a(v_srcroot, v_omitted_from_a);
            IF NOT v_omitted_from_a THEN
                v_out_obj.put('FromA', v_result_from_a);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('from_a') THEN
                    v_errors('from_a') := SQLERRM;
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
                v_payload.put('mapping', 'keyword_fields');
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
                v_payload.put('mapping', 'keyword_fields');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_keyword_fields;

    PROCEDURE map_keyword_fields_safe (
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
            v_result_number VARCHAR2(4000 CHAR);
            v_omitted_number BOOLEAN;
        BEGIN
            v_result_number := fn_keyword_fields_number(v_srcroot, v_omitted_number);
            IF NOT v_omitted_number THEN
                v_out_obj.put('Number', v_result_number);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number') THEN
                    v_errors('number') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_from_a NUMBER;
            v_omitted_from_a BOOLEAN;
        BEGIN
            v_result_from_a := fn_keyword_fields_from_a(v_srcroot, v_omitted_from_a);
            IF NOT v_omitted_from_a THEN
                v_out_obj.put('FromA', v_result_from_a);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('from_a') THEN
                    v_errors('from_a') := SQLERRM;
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
    END map_keyword_fields_safe;
END J2JME_MAP_KEYWORD_FIELDS;
/
