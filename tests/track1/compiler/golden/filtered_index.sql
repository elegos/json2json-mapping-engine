CREATE OR REPLACE PACKAGE FILTERED_INDEX AS
    PROCEDURE map_filtered_index (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_filtered_index_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END FILTERED_INDEX;
/

CREATE OR REPLACE PACKAGE BODY FILTERED_INDEX AS
    FUNCTION fn_filtered_index_active_rule(p_i IN NUMBER, p_itm IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_active_rule__dc JSON_OBJECT_T;
        v_val_active_rule__v0 NUMBER;
        v_val_active_rule__v1 VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_active_rule__dc := JSON_OBJECT_T();
        v_val_active_rule__v0 := p_i;
        IF v_val_active_rule__v0 IS NOT NULL THEN
            v_active_rule__dc.put('Pos', v_val_active_rule__v0);
        END IF;
        v_val_active_rule__v1 := p_itm.get_String('id');
        IF v_val_active_rule__v1 IS NOT NULL THEN
            v_active_rule__dc.put('Id', v_val_active_rule__v1);
        END IF;
        RETURN v_active_rule__dc;
    END fn_filtered_index_active_rule;

    FUNCTION fn_filtered_index_big_rule(p_j IN NUMBER, p_itm IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_big_rule__dc JSON_OBJECT_T;
        v_val_big_rule__v0 NUMBER;
        v_val_big_rule__v1 VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_big_rule__dc := JSON_OBJECT_T();
        v_val_big_rule__v0 := p_j;
        IF v_val_big_rule__v0 IS NOT NULL THEN
            v_big_rule__dc.put('Pos', v_val_big_rule__v0);
        END IF;
        v_val_big_rule__v1 := p_itm.get_String('id');
        IF v_val_big_rule__v1 IS NOT NULL THEN
            v_big_rule__dc.put('Id', v_val_big_rule__v1);
        END IF;
        RETURN v_big_rule__dc;
    END fn_filtered_index_big_rule;

    PROCEDURE map_filtered_index (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_arr_Actives JSON_ARRAY_T := JSON_ARRAY_T();
        v_arr_Bigs JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
            v_cnt_0 NUMBER := 1;
            v_cnt_1 NUMBER := 0;
        BEGIN
            IF v_forarr_0 IS NOT NULL THEN
                DECLARE
                    TYPE t_key_0_0 IS TABLE OF JSON_ELEMENT_T INDEX BY PLS_INTEGER;
                    TYPE t_ord_0_0 IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;
                    v_sortkey_0_0 t_key_0_0;
                    v_sortord_0_0 t_ord_0_0;
                    v_sorted_0_0 JSON_ARRAY_T := JSON_ARRAY_T();
                    v_sorttmp_0_0 PLS_INTEGER;
                    v_sortj_0_0 PLS_INTEGER;
                    FUNCTION v_sortnul_0_0(p IN PLS_INTEGER) RETURN BOOLEAN IS
                    BEGIN RETURN v_sortkey_0_0(p) IS NULL OR v_sortkey_0_0(p).is_Null; END;
                    FUNCTION v_sortcmp_0_0(a IN PLS_INTEGER, b IN PLS_INTEGER) RETURN PLS_INTEGER IS
                    BEGIN
                        IF v_sortnul_0_0(a) THEN RETURN CASE WHEN v_sortnul_0_0(b) THEN 0 ELSE 1 END; END IF;
                        IF v_sortnul_0_0(b) THEN RETURN -1; END IF;
                        IF v_sortkey_0_0(a).compare_to(v_sortkey_0_0(b)) < 0 THEN RETURN -1; END IF;
                        IF v_sortkey_0_0(a).compare_to(v_sortkey_0_0(b)) > 0 THEN RETURN 1; END IF;
                        RETURN 0;
                    END;
                BEGIN
                    FOR v_sorti_0_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                        v_sortkey_0_0(v_sorti_0_0) := TREAT(v_forarr_0.get(v_sorti_0_0) AS JSON_OBJECT_T).get('price');
                        v_sortord_0_0(v_sorti_0_0) := v_sorti_0_0;
                    END LOOP;
                    FOR v_sortk_0_0 IN 1 .. v_forarr_0.get_size - 1 LOOP
                        v_sorttmp_0_0 := v_sortord_0_0(v_sortk_0_0);
                        v_sortj_0_0 := v_sortk_0_0 - 1;
                        WHILE v_sortj_0_0 >= 0 AND v_sortcmp_0_0(v_sortord_0_0(v_sortj_0_0), v_sorttmp_0_0) > 0 LOOP
                            v_sortord_0_0(v_sortj_0_0 + 1) := v_sortord_0_0(v_sortj_0_0);
                            v_sortj_0_0 := v_sortj_0_0 - 1;
                        END LOOP;
                        v_sortord_0_0(v_sortj_0_0 + 1) := v_sorttmp_0_0;
                    END LOOP;
                    FOR v_sorti_0_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                        v_sorted_0_0.append(v_forarr_0.get(v_sortord_0_0(v_sorti_0_0)));
                    END LOOP;
                    v_forarr_0 := v_sorted_0_0;
                END;
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_itm JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    v_i NUMBER;
                    v_j NUMBER;
                    BEGIN
                        IF (v_itm.get_String('status') = 'A') THEN
                            v_i := v_cnt_0;
                            v_cnt_0 := v_cnt_0 + 1;
                            DECLARE
                                v_result_active_rule JSON_OBJECT_T;
                                v_omitted_active_rule BOOLEAN;
                            BEGIN
                                v_result_active_rule := fn_filtered_index_active_rule(v_i, v_itm, v_omitted_active_rule);
                                IF NOT v_omitted_active_rule THEN
                                    v_arr_Actives.append(v_result_active_rule);
                                END IF;
                            EXCEPTION
                                WHEN OTHERS THEN
                                    IF NOT v_errors.EXISTS('active_rule') THEN
                                        v_errors('active_rule') := SQLERRM;
                                    END IF;
                            END;
                        END IF;
                        IF (v_itm.get_Number('price') > 5) THEN
                            v_j := v_cnt_1;
                            v_cnt_1 := v_cnt_1 + 1;
                            DECLARE
                                v_result_big_rule JSON_OBJECT_T;
                                v_omitted_big_rule BOOLEAN;
                            BEGIN
                                v_result_big_rule := fn_filtered_index_big_rule(v_j, v_itm, v_omitted_big_rule);
                                IF NOT v_omitted_big_rule THEN
                                    v_arr_Bigs.append(v_result_big_rule);
                                END IF;
                            EXCEPTION
                                WHEN OTHERS THEN
                                    IF NOT v_errors.EXISTS('big_rule') THEN
                                        v_errors('big_rule') := SQLERRM;
                                    END IF;
                            END;
                        END IF;
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
                v_payload.put('mapping', 'filtered_index');
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
                v_payload.put('mapping', 'filtered_index');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        v_out_obj.put('Actives', v_arr_Actives);
        v_out_obj.put('Bigs', v_arr_Bigs);
        p_out := v_out_obj.TO_CLOB();
    END map_filtered_index;

    PROCEDURE map_filtered_index_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_arr_Actives JSON_ARRAY_T := JSON_ARRAY_T();
        v_arr_Bigs JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_forarr_0 JSON_ARRAY_T := v_srcroot.get_Array('items');
            v_cnt_0 NUMBER := 1;
            v_cnt_1 NUMBER := 0;
        BEGIN
            IF v_forarr_0 IS NOT NULL THEN
                DECLARE
                    TYPE t_key_0_0 IS TABLE OF JSON_ELEMENT_T INDEX BY PLS_INTEGER;
                    TYPE t_ord_0_0 IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;
                    v_sortkey_0_0 t_key_0_0;
                    v_sortord_0_0 t_ord_0_0;
                    v_sorted_0_0 JSON_ARRAY_T := JSON_ARRAY_T();
                    v_sorttmp_0_0 PLS_INTEGER;
                    v_sortj_0_0 PLS_INTEGER;
                    FUNCTION v_sortnul_0_0(p IN PLS_INTEGER) RETURN BOOLEAN IS
                    BEGIN RETURN v_sortkey_0_0(p) IS NULL OR v_sortkey_0_0(p).is_Null; END;
                    FUNCTION v_sortcmp_0_0(a IN PLS_INTEGER, b IN PLS_INTEGER) RETURN PLS_INTEGER IS
                    BEGIN
                        IF v_sortnul_0_0(a) THEN RETURN CASE WHEN v_sortnul_0_0(b) THEN 0 ELSE 1 END; END IF;
                        IF v_sortnul_0_0(b) THEN RETURN -1; END IF;
                        IF v_sortkey_0_0(a).compare_to(v_sortkey_0_0(b)) < 0 THEN RETURN -1; END IF;
                        IF v_sortkey_0_0(a).compare_to(v_sortkey_0_0(b)) > 0 THEN RETURN 1; END IF;
                        RETURN 0;
                    END;
                BEGIN
                    FOR v_sorti_0_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                        v_sortkey_0_0(v_sorti_0_0) := TREAT(v_forarr_0.get(v_sorti_0_0) AS JSON_OBJECT_T).get('price');
                        v_sortord_0_0(v_sorti_0_0) := v_sorti_0_0;
                    END LOOP;
                    FOR v_sortk_0_0 IN 1 .. v_forarr_0.get_size - 1 LOOP
                        v_sorttmp_0_0 := v_sortord_0_0(v_sortk_0_0);
                        v_sortj_0_0 := v_sortk_0_0 - 1;
                        WHILE v_sortj_0_0 >= 0 AND v_sortcmp_0_0(v_sortord_0_0(v_sortj_0_0), v_sorttmp_0_0) > 0 LOOP
                            v_sortord_0_0(v_sortj_0_0 + 1) := v_sortord_0_0(v_sortj_0_0);
                            v_sortj_0_0 := v_sortj_0_0 - 1;
                        END LOOP;
                        v_sortord_0_0(v_sortj_0_0 + 1) := v_sorttmp_0_0;
                    END LOOP;
                    FOR v_sorti_0_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                        v_sorted_0_0.append(v_forarr_0.get(v_sortord_0_0(v_sorti_0_0)));
                    END LOOP;
                    v_forarr_0 := v_sorted_0_0;
                END;
                FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                    DECLARE
                        v_itm JSON_OBJECT_T := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                    v_i NUMBER;
                    v_j NUMBER;
                    BEGIN
                        IF (v_itm.get_String('status') = 'A') THEN
                            v_i := v_cnt_0;
                            v_cnt_0 := v_cnt_0 + 1;
                            DECLARE
                                v_result_active_rule JSON_OBJECT_T;
                                v_omitted_active_rule BOOLEAN;
                            BEGIN
                                v_result_active_rule := fn_filtered_index_active_rule(v_i, v_itm, v_omitted_active_rule);
                                IF NOT v_omitted_active_rule THEN
                                    v_arr_Actives.append(v_result_active_rule);
                                END IF;
                            EXCEPTION
                                WHEN OTHERS THEN
                                    IF NOT v_errors.EXISTS('active_rule') THEN
                                        v_errors('active_rule') := SQLERRM;
                                    END IF;
                            END;
                        END IF;
                        IF (v_itm.get_Number('price') > 5) THEN
                            v_j := v_cnt_1;
                            v_cnt_1 := v_cnt_1 + 1;
                            DECLARE
                                v_result_big_rule JSON_OBJECT_T;
                                v_omitted_big_rule BOOLEAN;
                            BEGIN
                                v_result_big_rule := fn_filtered_index_big_rule(v_j, v_itm, v_omitted_big_rule);
                                IF NOT v_omitted_big_rule THEN
                                    v_arr_Bigs.append(v_result_big_rule);
                                END IF;
                            EXCEPTION
                                WHEN OTHERS THEN
                                    IF NOT v_errors.EXISTS('big_rule') THEN
                                        v_errors('big_rule') := SQLERRM;
                                    END IF;
                            END;
                        END IF;
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
        v_out_obj.put('Actives', v_arr_Actives);
        v_out_obj.put('Bigs', v_arr_Bigs);
        p_out := v_out_obj.TO_CLOB();
    END map_filtered_index_safe;
END FILTERED_INDEX;
/
