CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_DOCUMENT_LOOP AS
    PROCEDURE map_document_loop (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_document_loop_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_DOCUMENT_LOOP;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_DOCUMENT_LOOP AS
    FUNCTION fn_document_loop_entry(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_entry__dc JSON_OBJECT_T;
        v_val_entry__v0 VARCHAR2(4000 CHAR);
        v_val_entry__v1 VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_entry__dc := JSON_OBJECT_T();
        v_val_entry__v0 := p_src.get_String('id');
        IF v_val_entry__v0 IS NOT NULL THEN
            v_entry__dc.put('Key', v_val_entry__v0);
        END IF;
        v_val_entry__v1 := (p_src.get_String('id') || '/' || p_src.get_String('name'));
        IF v_val_entry__v1 IS NOT NULL THEN
            v_entry__dc.put('Label', v_val_entry__v1);
        END IF;
        RETURN v_entry__dc;
    END fn_document_loop_entry;

    FUNCTION fn_document_loop_fine(p_root IN JSON_OBJECT_T, p_f IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_fine__dc JSON_OBJECT_T;
        v_val_fine__v0 VARCHAR2(4000 CHAR);
        v_val_fine__v1 VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_fine__dc := JSON_OBJECT_T();
        v_val_fine__v0 := 'fine';
        IF v_val_fine__v0 IS NOT NULL THEN
            v_fine__dc.put('Key', v_val_fine__v0);
        END IF;
        v_val_fine__v1 := MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_f.get('amount'));
        IF v_val_fine__v1 IS NOT NULL THEN
            v_fine__dc.put('Label', v_val_fine__v1);
        END IF;
        RETURN v_fine__dc;
    END fn_document_loop_fine;

    PROCEDURE map_document_loop (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_arr_Entries JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_forarr_0 JSON_ARRAY_T := JSON_ARRAY_T();
        BEGIN
            v_forarr_0.append(v_srcroot);
            IF v_forarr_0 IS NOT NULL THEN
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_src JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_entry JSON_OBJECT_T;
                            v_omitted_entry BOOLEAN;
                        BEGIN
                            v_result_entry := fn_document_loop_entry(v_srcroot, v_src, v_omitted_entry);
                            IF NOT v_omitted_entry THEN
                                v_arr_Entries.append(v_result_entry);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('entry') THEN
                                    v_errors('entry') := SQLERRM;
                                END IF;
                        END;
                    END;
                END LOOP;
            END IF;
        END;
        DECLARE
            v_forarr_1 JSON_ARRAY_T := v_srcroot.get_Array('fines');
        BEGIN
            IF v_forarr_1 IS NOT NULL THEN
                FOR v_i_1 IN 0 .. v_forarr_1.get_size - 1 LOOP
                    DECLARE
                        v_f JSON_OBJECT_T := TREAT(v_forarr_1.get(v_i_1) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_fine JSON_OBJECT_T;
                            v_omitted_fine BOOLEAN;
                        BEGIN
                            v_result_fine := fn_document_loop_fine(v_srcroot, v_f, v_omitted_fine);
                            IF NOT v_omitted_fine THEN
                                v_arr_Entries.append(v_result_fine);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('fine') THEN
                                    v_errors('fine') := SQLERRM;
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
                v_payload.put('mapping', 'document_loop');
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
                v_payload.put('mapping', 'document_loop');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        v_out_obj.put('Entries', v_arr_Entries);
        p_out := v_out_obj.TO_CLOB();
    END map_document_loop;

    PROCEDURE map_document_loop_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_arr_Entries JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_forarr_0 JSON_ARRAY_T := JSON_ARRAY_T();
        BEGIN
            v_forarr_0.append(v_srcroot);
            IF v_forarr_0 IS NOT NULL THEN
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_src JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_entry JSON_OBJECT_T;
                            v_omitted_entry BOOLEAN;
                        BEGIN
                            v_result_entry := fn_document_loop_entry(v_srcroot, v_src, v_omitted_entry);
                            IF NOT v_omitted_entry THEN
                                v_arr_Entries.append(v_result_entry);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('entry') THEN
                                    v_errors('entry') := SQLERRM;
                                END IF;
                        END;
                    END;
                END LOOP;
            END IF;
        END;
        DECLARE
            v_forarr_1 JSON_ARRAY_T := v_srcroot.get_Array('fines');
        BEGIN
            IF v_forarr_1 IS NOT NULL THEN
                FOR v_i_1 IN 0 .. v_forarr_1.get_size - 1 LOOP
                    DECLARE
                        v_f JSON_OBJECT_T := TREAT(v_forarr_1.get(v_i_1) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_fine JSON_OBJECT_T;
                            v_omitted_fine BOOLEAN;
                        BEGIN
                            v_result_fine := fn_document_loop_fine(v_srcroot, v_f, v_omitted_fine);
                            IF NOT v_omitted_fine THEN
                                v_arr_Entries.append(v_result_fine);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('fine') THEN
                                    v_errors('fine') := SQLERRM;
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
        v_out_obj.put('Entries', v_arr_Entries);
        p_out := v_out_obj.TO_CLOB();
    END map_document_loop_safe;
END J2JME_MAP_DOCUMENT_LOOP;
/
