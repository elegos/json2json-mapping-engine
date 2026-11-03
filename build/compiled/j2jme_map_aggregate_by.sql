CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_AGGREGATE_BY AS
    PROCEDURE map_aggregate_by (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_aggregate_by_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_AGGREGATE_BY;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_AGGREGATE_BY AS
    FUNCTION fn_aggregate_by_ok_count(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_ok_count__agg NUMBER;
        v_aggarr_0 JSON_ARRAY_T;
        v_aggel_0 JSON_OBJECT_T;
        v_aggn_0 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_0 := p_root.get_Array('samples');
        v_aggn_0 := 0;
        IF v_aggarr_0 IS NOT NULL THEN
            FOR v_aggk_0 IN 0 .. v_aggarr_0.get_size - 1 LOOP
                v_aggel_0 := TREAT(v_aggarr_0.get(v_aggk_0) AS JSON_OBJECT_T);
                IF (v_aggel_0.get_String('quality') = 'OK') THEN
                    v_aggn_0 := v_aggn_0 + 1;
                END IF;
            END LOOP;
        END IF;
        v_ok_count__agg := v_aggn_0;
        IF v_ok_count__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ok_count__agg;
    END fn_aggregate_by_ok_count;

    FUNCTION fn_aggregate_by_ok_total(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_ok_total__agg NUMBER;
        v_aggarr_1 JSON_ARRAY_T;
        v_aggel_1 JSON_OBJECT_T;
        v_aggval_1 NUMBER;
        v_aggacc_1 NUMBER;
        v_aggn_1 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_1 := p_root.get_Array('samples');
        v_aggacc_1 := 0;
        v_aggn_1 := 0;
        IF v_aggarr_1 IS NOT NULL THEN
            FOR v_aggk_1 IN 0 .. v_aggarr_1.get_size - 1 LOOP
                v_aggel_1 := TREAT(v_aggarr_1.get(v_aggk_1) AS JSON_OBJECT_T);
                IF (v_aggel_1.get_String('quality') = 'OK') THEN
                    v_aggval_1 := v_aggel_1.get_Number('value');
                    IF v_aggval_1 IS NOT NULL THEN
                        v_aggacc_1 := v_aggacc_1 + v_aggval_1;
                        v_aggn_1 := v_aggn_1 + 1;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        v_ok_total__agg := v_aggacc_1;
        IF v_ok_total__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ok_total__agg;
    END fn_aggregate_by_ok_total;

    FUNCTION fn_aggregate_by_big_ok_total(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_big_ok_total__agg NUMBER;
        v_aggarr_2 JSON_ARRAY_T;
        v_aggel_2 JSON_OBJECT_T;
        v_aggval_2 NUMBER;
        v_aggacc_2 NUMBER;
        v_aggn_2 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_2 := p_root.get_Array('samples');
        v_aggacc_2 := 0;
        v_aggn_2 := 0;
        IF v_aggarr_2 IS NOT NULL THEN
            FOR v_aggk_2 IN 0 .. v_aggarr_2.get_size - 1 LOOP
                v_aggel_2 := TREAT(v_aggarr_2.get(v_aggk_2) AS JSON_OBJECT_T);
                IF (v_aggel_2.get_String('quality') = 'OK') AND (v_aggel_2.get_Number('value') > 10) THEN
                    v_aggval_2 := v_aggel_2.get_Number('value');
                    IF v_aggval_2 IS NOT NULL THEN
                        v_aggacc_2 := v_aggacc_2 + v_aggval_2;
                        v_aggn_2 := v_aggn_2 + 1;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        v_big_ok_total__agg := v_aggacc_2;
        IF v_big_ok_total__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_big_ok_total__agg;
    END fn_aggregate_by_big_ok_total;

    FUNCTION fn_aggregate_by_abs_total(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_abs_total__agg NUMBER;
        v_aggarr_3 JSON_ARRAY_T;
        v_aggel_3 JSON_OBJECT_T;
        v_aggval_3 NUMBER;
        v_aggacc_3 NUMBER;
        v_aggn_3 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_3 := p_root.get_Array('readings');
        v_aggacc_3 := 0;
        v_aggn_3 := 0;
        IF v_aggarr_3 IS NOT NULL THEN
            FOR v_aggk_3 IN 0 .. v_aggarr_3.get_size - 1 LOOP
                v_aggel_3 := TREAT(v_aggarr_3.get(v_aggk_3) AS JSON_OBJECT_T);
                v_aggval_3 := ABS(v_aggel_3.get_Number('quantity'));
                IF v_aggval_3 IS NOT NULL THEN
                    v_aggacc_3 := v_aggacc_3 + v_aggval_3;
                    v_aggn_3 := v_aggn_3 + 1;
                END IF;
            END LOOP;
        END IF;
        v_abs_total__agg := v_aggacc_3;
        IF v_abs_total__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_abs_total__agg;
    END fn_aggregate_by_abs_total;

    FUNCTION fn_aggregate_by_ok_max(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_ok_max__agg NUMBER;
        v_aggarr_4 JSON_ARRAY_T;
        v_aggel_4 JSON_OBJECT_T;
        v_aggval_4 NUMBER;
        v_aggacc_4 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_4 := p_root.get_Array('readings');
        v_aggacc_4 := NULL;
        IF v_aggarr_4 IS NOT NULL THEN
            FOR v_aggk_4 IN 0 .. v_aggarr_4.get_size - 1 LOOP
                v_aggel_4 := TREAT(v_aggarr_4.get(v_aggk_4) AS JSON_OBJECT_T);
                IF (v_aggel_4.get_String('quality') = 'OK') THEN
                    v_aggval_4 := v_aggel_4.get_Number('quantity');
                    IF v_aggval_4 IS NOT NULL THEN
                        IF v_aggacc_4 IS NULL OR v_aggval_4 > v_aggacc_4 THEN v_aggacc_4 := v_aggval_4; END IF;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        v_ok_max__agg := v_aggacc_4;
        IF v_ok_max__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ok_max__agg;
    END fn_aggregate_by_ok_max;

    FUNCTION fn_aggregate_by_ok_min(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_ok_min__agg NUMBER;
        v_aggarr_5 JSON_ARRAY_T;
        v_aggel_5 JSON_OBJECT_T;
        v_aggval_5 NUMBER;
        v_aggacc_5 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_5 := p_root.get_Array('readings');
        v_aggacc_5 := NULL;
        IF v_aggarr_5 IS NOT NULL THEN
            FOR v_aggk_5 IN 0 .. v_aggarr_5.get_size - 1 LOOP
                v_aggel_5 := TREAT(v_aggarr_5.get(v_aggk_5) AS JSON_OBJECT_T);
                IF (v_aggel_5.get_String('quality') = 'OK') THEN
                    v_aggval_5 := (v_aggel_5.get_Number('quantity') * 2);
                    IF v_aggval_5 IS NOT NULL THEN
                        IF v_aggacc_5 IS NULL OR v_aggval_5 < v_aggacc_5 THEN v_aggacc_5 := v_aggval_5; END IF;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        v_ok_min__agg := v_aggacc_5;
        IF v_ok_min__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ok_min__agg;
    END fn_aggregate_by_ok_min;

    FUNCTION fn_aggregate_by_ok_avg(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_ok_avg__agg NUMBER;
        v_aggarr_6 JSON_ARRAY_T;
        v_aggel_6 JSON_OBJECT_T;
        v_aggval_6 NUMBER;
        v_aggacc_6 NUMBER;
        v_aggn_6 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_6 := p_root.get_Array('readings');
        v_aggacc_6 := 0;
        v_aggn_6 := 0;
        IF v_aggarr_6 IS NOT NULL THEN
            FOR v_aggk_6 IN 0 .. v_aggarr_6.get_size - 1 LOOP
                v_aggel_6 := TREAT(v_aggarr_6.get(v_aggk_6) AS JSON_OBJECT_T);
                IF (v_aggel_6.get_String('quality') = 'OK') THEN
                    v_aggval_6 := v_aggel_6.get_Number('quantity');
                    IF v_aggval_6 IS NOT NULL THEN
                        v_aggacc_6 := v_aggacc_6 + v_aggval_6;
                        v_aggn_6 := v_aggn_6 + 1;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        IF v_aggn_6 > 0 THEN v_ok_avg__agg := v_aggacc_6 / v_aggn_6; END IF;
        IF v_ok_avg__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ok_avg__agg;
    END fn_aggregate_by_ok_avg;

    FUNCTION fn_aggregate_by_plain_total(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_plain_total__agg NUMBER;
        v_aggarr_7 JSON_ARRAY_T;
        v_aggel_7 JSON_OBJECT_T;
        v_aggval_7 NUMBER;
        v_aggacc_7 NUMBER;
        v_aggn_7 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_7 := p_root.get_Array('samples');
        v_aggacc_7 := 0;
        v_aggn_7 := 0;
        IF v_aggarr_7 IS NOT NULL THEN
            FOR v_aggk_7 IN 0 .. v_aggarr_7.get_size - 1 LOOP
                v_aggel_7 := TREAT(v_aggarr_7.get(v_aggk_7) AS JSON_OBJECT_T);
                v_aggval_7 := v_aggel_7.get_Number('value');
                IF v_aggval_7 IS NOT NULL THEN
                    v_aggacc_7 := v_aggacc_7 + v_aggval_7;
                    v_aggn_7 := v_aggn_7 + 1;
                END IF;
            END LOOP;
        END IF;
        v_plain_total__agg := v_aggacc_7;
        IF v_plain_total__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_plain_total__agg;
    END fn_aggregate_by_plain_total;

    FUNCTION fn_aggregate_by_plain_count(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_plain_count__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_plain_count__ret := (CASE WHEN p_root.get_Array('samples') IS NULL THEN 0 ELSE p_root.get_Array('samples').get_size END);
        IF v_plain_count__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_plain_count__ret;
    END fn_aggregate_by_plain_count;

    PROCEDURE map_aggregate_by (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_ok_count NUMBER;
            v_omitted_ok_count BOOLEAN;
        BEGIN
            v_result_ok_count := fn_aggregate_by_ok_count(v_srcroot, v_omitted_ok_count);
            IF NOT v_omitted_ok_count THEN
                v_out_obj.put('OkCount', v_result_ok_count);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_count') THEN
                    v_errors('ok_count') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_total NUMBER;
            v_omitted_ok_total BOOLEAN;
        BEGIN
            v_result_ok_total := fn_aggregate_by_ok_total(v_srcroot, v_omitted_ok_total);
            IF NOT v_omitted_ok_total THEN
                v_out_obj.put('OkTotal', v_result_ok_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_total') THEN
                    v_errors('ok_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_big_ok_total NUMBER;
            v_omitted_big_ok_total BOOLEAN;
        BEGIN
            v_result_big_ok_total := fn_aggregate_by_big_ok_total(v_srcroot, v_omitted_big_ok_total);
            IF NOT v_omitted_big_ok_total THEN
                v_out_obj.put('BigOkTotal', v_result_big_ok_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('big_ok_total') THEN
                    v_errors('big_ok_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_abs_total NUMBER;
            v_omitted_abs_total BOOLEAN;
        BEGIN
            v_result_abs_total := fn_aggregate_by_abs_total(v_srcroot, v_omitted_abs_total);
            IF NOT v_omitted_abs_total THEN
                v_out_obj.put('AbsTotal', v_result_abs_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('abs_total') THEN
                    v_errors('abs_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_max NUMBER;
            v_omitted_ok_max BOOLEAN;
        BEGIN
            v_result_ok_max := fn_aggregate_by_ok_max(v_srcroot, v_omitted_ok_max);
            IF NOT v_omitted_ok_max THEN
                v_out_obj.put('OkMax', v_result_ok_max);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_max') THEN
                    v_errors('ok_max') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_min NUMBER;
            v_omitted_ok_min BOOLEAN;
        BEGIN
            v_result_ok_min := fn_aggregate_by_ok_min(v_srcroot, v_omitted_ok_min);
            IF NOT v_omitted_ok_min THEN
                v_out_obj.put('OkMin', v_result_ok_min);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_min') THEN
                    v_errors('ok_min') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_avg NUMBER;
            v_omitted_ok_avg BOOLEAN;
        BEGIN
            v_result_ok_avg := fn_aggregate_by_ok_avg(v_srcroot, v_omitted_ok_avg);
            IF NOT v_omitted_ok_avg THEN
                v_out_obj.put('OkAvg', v_result_ok_avg);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_avg') THEN
                    v_errors('ok_avg') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_plain_total NUMBER;
            v_omitted_plain_total BOOLEAN;
        BEGIN
            v_result_plain_total := fn_aggregate_by_plain_total(v_srcroot, v_omitted_plain_total);
            IF NOT v_omitted_plain_total THEN
                v_out_obj.put('PlainTotal', v_result_plain_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('plain_total') THEN
                    v_errors('plain_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_plain_count NUMBER;
            v_omitted_plain_count BOOLEAN;
        BEGIN
            v_result_plain_count := fn_aggregate_by_plain_count(v_srcroot, v_omitted_plain_count);
            IF NOT v_omitted_plain_count THEN
                v_out_obj.put('PlainCount', v_result_plain_count);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('plain_count') THEN
                    v_errors('plain_count') := SQLERRM;
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
                v_payload.put('mapping', 'aggregate_by');
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
                v_payload.put('mapping', 'aggregate_by');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_aggregate_by;

    PROCEDURE map_aggregate_by_safe (
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
            v_result_ok_count NUMBER;
            v_omitted_ok_count BOOLEAN;
        BEGIN
            v_result_ok_count := fn_aggregate_by_ok_count(v_srcroot, v_omitted_ok_count);
            IF NOT v_omitted_ok_count THEN
                v_out_obj.put('OkCount', v_result_ok_count);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_count') THEN
                    v_errors('ok_count') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_total NUMBER;
            v_omitted_ok_total BOOLEAN;
        BEGIN
            v_result_ok_total := fn_aggregate_by_ok_total(v_srcroot, v_omitted_ok_total);
            IF NOT v_omitted_ok_total THEN
                v_out_obj.put('OkTotal', v_result_ok_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_total') THEN
                    v_errors('ok_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_big_ok_total NUMBER;
            v_omitted_big_ok_total BOOLEAN;
        BEGIN
            v_result_big_ok_total := fn_aggregate_by_big_ok_total(v_srcroot, v_omitted_big_ok_total);
            IF NOT v_omitted_big_ok_total THEN
                v_out_obj.put('BigOkTotal', v_result_big_ok_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('big_ok_total') THEN
                    v_errors('big_ok_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_abs_total NUMBER;
            v_omitted_abs_total BOOLEAN;
        BEGIN
            v_result_abs_total := fn_aggregate_by_abs_total(v_srcroot, v_omitted_abs_total);
            IF NOT v_omitted_abs_total THEN
                v_out_obj.put('AbsTotal', v_result_abs_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('abs_total') THEN
                    v_errors('abs_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_max NUMBER;
            v_omitted_ok_max BOOLEAN;
        BEGIN
            v_result_ok_max := fn_aggregate_by_ok_max(v_srcroot, v_omitted_ok_max);
            IF NOT v_omitted_ok_max THEN
                v_out_obj.put('OkMax', v_result_ok_max);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_max') THEN
                    v_errors('ok_max') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_min NUMBER;
            v_omitted_ok_min BOOLEAN;
        BEGIN
            v_result_ok_min := fn_aggregate_by_ok_min(v_srcroot, v_omitted_ok_min);
            IF NOT v_omitted_ok_min THEN
                v_out_obj.put('OkMin', v_result_ok_min);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_min') THEN
                    v_errors('ok_min') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_avg NUMBER;
            v_omitted_ok_avg BOOLEAN;
        BEGIN
            v_result_ok_avg := fn_aggregate_by_ok_avg(v_srcroot, v_omitted_ok_avg);
            IF NOT v_omitted_ok_avg THEN
                v_out_obj.put('OkAvg', v_result_ok_avg);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_avg') THEN
                    v_errors('ok_avg') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_plain_total NUMBER;
            v_omitted_plain_total BOOLEAN;
        BEGIN
            v_result_plain_total := fn_aggregate_by_plain_total(v_srcroot, v_omitted_plain_total);
            IF NOT v_omitted_plain_total THEN
                v_out_obj.put('PlainTotal', v_result_plain_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('plain_total') THEN
                    v_errors('plain_total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_plain_count NUMBER;
            v_omitted_plain_count BOOLEAN;
        BEGIN
            v_result_plain_count := fn_aggregate_by_plain_count(v_srcroot, v_omitted_plain_count);
            IF NOT v_omitted_plain_count THEN
                v_out_obj.put('PlainCount', v_result_plain_count);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('plain_count') THEN
                    v_errors('plain_count') := SQLERRM;
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
    END map_aggregate_by_safe;
END J2JME_MAP_AGGREGATE_BY;
/
