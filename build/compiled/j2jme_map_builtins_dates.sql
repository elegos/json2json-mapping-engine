CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_BUILTINS_DATES AS
    PROCEDURE map_builtins_dates (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_dates_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_BUILTINS_DATES;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_BUILTINS_DATES AS
    FUNCTION fn_builtins_dates_as_written(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_as_written__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_as_written__ret := MAPPING_OWNER.J2JME_FUNCTIONS.rfc3339_normalize(p_root.get_String('ts'));
        IF v_as_written__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_as_written__ret;
    END fn_builtins_dates_as_written;

    FUNCTION fn_builtins_dates_millis(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_millis__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_millis__ret := MAPPING_OWNER.J2JME_FUNCTIONS.rfc3339_normalize(p_root.get_String('ts'), 3);
        IF v_millis__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_millis__ret;
    END fn_builtins_dates_millis;

    FUNCTION fn_builtins_dates_no_fraction(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_no_fraction__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_no_fraction__ret := MAPPING_OWNER.J2JME_FUNCTIONS.rfc3339_normalize(p_root.get_String('ts'), 0);
        IF v_no_fraction__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_no_fraction__ret;
    END fn_builtins_dates_no_fraction;

    FUNCTION fn_builtins_dates_millis_utc(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_millis_utc__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_millis_utc__ret := MAPPING_OWNER.J2JME_FUNCTIONS.to_utc(p_root.get_String('ts'), 3);
        IF v_millis_utc__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_millis_utc__ret;
    END fn_builtins_dates_millis_utc;

    FUNCTION fn_builtins_dates_parsed(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_parsed__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_parsed__ret := MAPPING_OWNER.J2JME_FUNCTIONS.parse_timestamp(p_root.get_String('us'), 'MON DD, YYYY, HH12:MI:SS AM');
        IF v_parsed__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_parsed__ret;
    END fn_builtins_dates_parsed;

    FUNCTION fn_builtins_dates_printed(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_printed__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_printed__ret := MAPPING_OWNER.J2JME_FUNCTIONS.format_date(MAPPING_OWNER.J2JME_FUNCTIONS.parse_timestamp(p_root.get_String('us'), 'MON DD, YYYY, HH12:MI:SS AM'), 'DD-MM-YYYY HH24:MI:SS');
        IF v_printed__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_printed__ret;
    END fn_builtins_dates_printed;

    FUNCTION fn_builtins_dates_days_overdue(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_days_overdue__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_days_overdue__ret := (TO_DATE(SUBSTR(TRIM(MAPPING_OWNER.J2JME_FUNCTIONS.parse_timestamp(p_root.get_String('us'), 'MON DD, YYYY, HH12:MI:SS AM')), 1, 10), 'YYYY-MM-DD') - TO_DATE(SUBSTR(TRIM(p_root.get_String('due')), 1, 10), 'YYYY-MM-DD'));
        IF v_days_overdue__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_days_overdue__ret;
    END fn_builtins_dates_days_overdue;

    FUNCTION fn_builtins_dates_later(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_later__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_later__ret := TO_CHAR(TO_DATE(SUBSTR(TRIM(p_root.get_String('date')), 1, 10), 'YYYY-MM-DD') + TRUNC(p_root.get_Number('n')), 'YYYY-MM-DD');
        IF v_later__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_later__ret;
    END fn_builtins_dates_later;

    FUNCTION fn_builtins_dates_earlier(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_earlier__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_earlier__ret := TO_CHAR(TO_DATE(SUBSTR(TRIM(p_root.get_String('date')), 1, 10), 'YYYY-MM-DD') + TRUNC((0 - 5)), 'YYYY-MM-DD');
        IF v_earlier__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_earlier__ret;
    END fn_builtins_dates_earlier;

    FUNCTION fn_builtins_dates_last_part(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_last_part__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_last_part__ret := (CASE WHEN INSTR(p_root.get_String('id'), '-', -1) = 0 THEN p_root.get_String('id') ELSE SUBSTR(p_root.get_String('id'), INSTR(p_root.get_String('id'), '-', -1) + LENGTH('-')) END);
        IF v_last_part__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_last_part__ret;
    END fn_builtins_dates_last_part;

    FUNCTION fn_builtins_dates_tags(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_tags__agg VARCHAR2(4000 CHAR);
        v_aggarr_0 JSON_ARRAY_T;
        v_aggacc_0 VARCHAR2(32767);
        v_aggval_0 VARCHAR2(32767);
    BEGIN
        p_omitted := FALSE;
        v_aggarr_0 := p_root.get_Array('tags');
        v_aggacc_0 := NULL;
        IF v_aggarr_0 IS NOT NULL THEN
            FOR v_aggk_0 IN 0 .. v_aggarr_0.get_size - 1 LOOP
                v_aggval_0 := v_aggarr_0.get_String(v_aggk_0);
                IF v_aggval_0 IS NOT NULL THEN
                    IF v_aggacc_0 IS NULL THEN v_aggacc_0 := v_aggval_0; ELSE v_aggacc_0 := v_aggacc_0 || ', ' || v_aggval_0; END IF;
                END IF;
            END LOOP;
        END IF;
        v_tags__agg := v_aggacc_0;
        IF v_tags__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_tags__agg;
    END fn_builtins_dates_tags;

    FUNCTION fn_builtins_dates_glued(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_glued__agg VARCHAR2(4000 CHAR);
        v_aggarr_1 JSON_ARRAY_T;
        v_aggacc_1 VARCHAR2(32767);
        v_aggval_1 VARCHAR2(32767);
    BEGIN
        p_omitted := FALSE;
        v_aggarr_1 := p_root.get_Array('tags');
        v_aggacc_1 := NULL;
        IF v_aggarr_1 IS NOT NULL THEN
            FOR v_aggk_1 IN 0 .. v_aggarr_1.get_size - 1 LOOP
                v_aggval_1 := v_aggarr_1.get_String(v_aggk_1);
                IF v_aggval_1 IS NOT NULL THEN
                    IF v_aggacc_1 IS NULL THEN v_aggacc_1 := v_aggval_1; ELSE v_aggacc_1 := v_aggacc_1 || '' || v_aggval_1; END IF;
                END IF;
            END LOOP;
        END IF;
        v_glued__agg := v_aggacc_1;
        IF v_glued__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_glued__agg;
    END fn_builtins_dates_glued;

    FUNCTION fn_builtins_dates_ok_ids(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_ok_ids__agg VARCHAR2(4000 CHAR);
        v_aggarr_2 JSON_ARRAY_T;
        v_aggel_2 JSON_OBJECT_T;
        v_aggval_2 VARCHAR2(4000 CHAR);
        v_aggacc_2 VARCHAR2(32767);
    BEGIN
        p_omitted := FALSE;
        v_aggarr_2 := p_root.get_Array('items');
        v_aggacc_2 := NULL;
        IF v_aggarr_2 IS NOT NULL THEN
            FOR v_aggk_2 IN 0 .. v_aggarr_2.get_size - 1 LOOP
                v_aggel_2 := TREAT(v_aggarr_2.get(v_aggk_2) AS JSON_OBJECT_T);
                IF MAPPING_OWNER.J2JME_FUNCTIONS.truthy(v_aggel_2.get('ok')) THEN
                    v_aggval_2 := MAPPING_OWNER.J2JME_FUNCTIONS.to_string(v_aggel_2.get('id'));
                    IF v_aggval_2 IS NOT NULL THEN
                        IF v_aggacc_2 IS NULL THEN v_aggacc_2 := v_aggval_2; ELSE v_aggacc_2 := v_aggacc_2 || '|' || v_aggval_2; END IF;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        v_ok_ids__agg := v_aggacc_2;
        IF v_ok_ids__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ok_ids__agg;
    END fn_builtins_dates_ok_ids;

    FUNCTION fn_builtins_dates_custom(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_custom__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_custom__ret := MAPPING_OWNER.J2JME_FUNCTIONS.parse_timestamp(p_root.get_String('us'), p_root.get_String('fmt'));
        IF v_custom__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_custom__ret;
    END fn_builtins_dates_custom;

    PROCEDURE map_builtins_dates (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_as_written VARCHAR2(4000 CHAR);
            v_omitted_as_written BOOLEAN;
        BEGIN
            v_result_as_written := fn_builtins_dates_as_written(v_srcroot, v_omitted_as_written);
            IF NOT v_omitted_as_written THEN
                v_out_obj.put('AsWritten', v_result_as_written);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('as_written') THEN
                    v_errors('as_written') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_millis VARCHAR2(4000 CHAR);
            v_omitted_millis BOOLEAN;
        BEGIN
            v_result_millis := fn_builtins_dates_millis(v_srcroot, v_omitted_millis);
            IF NOT v_omitted_millis THEN
                v_out_obj.put('Millis', v_result_millis);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('millis') THEN
                    v_errors('millis') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_no_fraction VARCHAR2(4000 CHAR);
            v_omitted_no_fraction BOOLEAN;
        BEGIN
            v_result_no_fraction := fn_builtins_dates_no_fraction(v_srcroot, v_omitted_no_fraction);
            IF NOT v_omitted_no_fraction THEN
                v_out_obj.put('NoFraction', v_result_no_fraction);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('no_fraction') THEN
                    v_errors('no_fraction') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_millis_utc VARCHAR2(4000 CHAR);
            v_omitted_millis_utc BOOLEAN;
        BEGIN
            v_result_millis_utc := fn_builtins_dates_millis_utc(v_srcroot, v_omitted_millis_utc);
            IF NOT v_omitted_millis_utc THEN
                v_out_obj.put('MillisUtc', v_result_millis_utc);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('millis_utc') THEN
                    v_errors('millis_utc') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_parsed VARCHAR2(4000 CHAR);
            v_omitted_parsed BOOLEAN;
        BEGIN
            v_result_parsed := fn_builtins_dates_parsed(v_srcroot, v_omitted_parsed);
            IF NOT v_omitted_parsed THEN
                v_out_obj.put('Parsed', v_result_parsed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('parsed') THEN
                    v_errors('parsed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_printed VARCHAR2(4000 CHAR);
            v_omitted_printed BOOLEAN;
        BEGIN
            v_result_printed := fn_builtins_dates_printed(v_srcroot, v_omitted_printed);
            IF NOT v_omitted_printed THEN
                v_out_obj.put('Printed', v_result_printed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('printed') THEN
                    v_errors('printed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_days_overdue NUMBER;
            v_omitted_days_overdue BOOLEAN;
        BEGIN
            v_result_days_overdue := fn_builtins_dates_days_overdue(v_srcroot, v_omitted_days_overdue);
            IF NOT v_omitted_days_overdue THEN
                v_out_obj.put('DaysOverdue', v_result_days_overdue);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('days_overdue') THEN
                    v_errors('days_overdue') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_later VARCHAR2(4000 CHAR);
            v_omitted_later BOOLEAN;
        BEGIN
            v_result_later := fn_builtins_dates_later(v_srcroot, v_omitted_later);
            IF NOT v_omitted_later THEN
                v_out_obj.put('Later', v_result_later);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('later') THEN
                    v_errors('later') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_earlier VARCHAR2(4000 CHAR);
            v_omitted_earlier BOOLEAN;
        BEGIN
            v_result_earlier := fn_builtins_dates_earlier(v_srcroot, v_omitted_earlier);
            IF NOT v_omitted_earlier THEN
                v_out_obj.put('Earlier', v_result_earlier);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('earlier') THEN
                    v_errors('earlier') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_last_part VARCHAR2(4000 CHAR);
            v_omitted_last_part BOOLEAN;
        BEGIN
            v_result_last_part := fn_builtins_dates_last_part(v_srcroot, v_omitted_last_part);
            IF NOT v_omitted_last_part THEN
                v_out_obj.put('LastPart', v_result_last_part);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('last_part') THEN
                    v_errors('last_part') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_tags VARCHAR2(4000 CHAR);
            v_omitted_tags BOOLEAN;
        BEGIN
            v_result_tags := fn_builtins_dates_tags(v_srcroot, v_omitted_tags);
            IF NOT v_omitted_tags THEN
                v_out_obj.put('Tags', v_result_tags);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('tags') THEN
                    v_errors('tags') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_glued VARCHAR2(4000 CHAR);
            v_omitted_glued BOOLEAN;
        BEGIN
            v_result_glued := fn_builtins_dates_glued(v_srcroot, v_omitted_glued);
            IF NOT v_omitted_glued THEN
                v_out_obj.put('Glued', v_result_glued);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('glued') THEN
                    v_errors('glued') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_ids VARCHAR2(4000 CHAR);
            v_omitted_ok_ids BOOLEAN;
        BEGIN
            v_result_ok_ids := fn_builtins_dates_ok_ids(v_srcroot, v_omitted_ok_ids);
            IF NOT v_omitted_ok_ids THEN
                v_out_obj.put('OkIds', v_result_ok_ids);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_ids') THEN
                    v_errors('ok_ids') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_custom VARCHAR2(4000 CHAR);
            v_omitted_custom BOOLEAN;
        BEGIN
            v_result_custom := fn_builtins_dates_custom(v_srcroot, v_omitted_custom);
            IF NOT v_omitted_custom THEN
                v_out_obj.put('Custom', v_result_custom);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('custom') THEN
                    v_errors('custom') := SQLERRM;
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
                v_payload.put('mapping', 'builtins_dates');
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
                v_payload.put('mapping', 'builtins_dates');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_builtins_dates;

    PROCEDURE map_builtins_dates_safe (
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
            v_result_as_written VARCHAR2(4000 CHAR);
            v_omitted_as_written BOOLEAN;
        BEGIN
            v_result_as_written := fn_builtins_dates_as_written(v_srcroot, v_omitted_as_written);
            IF NOT v_omitted_as_written THEN
                v_out_obj.put('AsWritten', v_result_as_written);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('as_written') THEN
                    v_errors('as_written') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_millis VARCHAR2(4000 CHAR);
            v_omitted_millis BOOLEAN;
        BEGIN
            v_result_millis := fn_builtins_dates_millis(v_srcroot, v_omitted_millis);
            IF NOT v_omitted_millis THEN
                v_out_obj.put('Millis', v_result_millis);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('millis') THEN
                    v_errors('millis') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_no_fraction VARCHAR2(4000 CHAR);
            v_omitted_no_fraction BOOLEAN;
        BEGIN
            v_result_no_fraction := fn_builtins_dates_no_fraction(v_srcroot, v_omitted_no_fraction);
            IF NOT v_omitted_no_fraction THEN
                v_out_obj.put('NoFraction', v_result_no_fraction);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('no_fraction') THEN
                    v_errors('no_fraction') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_millis_utc VARCHAR2(4000 CHAR);
            v_omitted_millis_utc BOOLEAN;
        BEGIN
            v_result_millis_utc := fn_builtins_dates_millis_utc(v_srcroot, v_omitted_millis_utc);
            IF NOT v_omitted_millis_utc THEN
                v_out_obj.put('MillisUtc', v_result_millis_utc);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('millis_utc') THEN
                    v_errors('millis_utc') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_parsed VARCHAR2(4000 CHAR);
            v_omitted_parsed BOOLEAN;
        BEGIN
            v_result_parsed := fn_builtins_dates_parsed(v_srcroot, v_omitted_parsed);
            IF NOT v_omitted_parsed THEN
                v_out_obj.put('Parsed', v_result_parsed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('parsed') THEN
                    v_errors('parsed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_printed VARCHAR2(4000 CHAR);
            v_omitted_printed BOOLEAN;
        BEGIN
            v_result_printed := fn_builtins_dates_printed(v_srcroot, v_omitted_printed);
            IF NOT v_omitted_printed THEN
                v_out_obj.put('Printed', v_result_printed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('printed') THEN
                    v_errors('printed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_days_overdue NUMBER;
            v_omitted_days_overdue BOOLEAN;
        BEGIN
            v_result_days_overdue := fn_builtins_dates_days_overdue(v_srcroot, v_omitted_days_overdue);
            IF NOT v_omitted_days_overdue THEN
                v_out_obj.put('DaysOverdue', v_result_days_overdue);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('days_overdue') THEN
                    v_errors('days_overdue') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_later VARCHAR2(4000 CHAR);
            v_omitted_later BOOLEAN;
        BEGIN
            v_result_later := fn_builtins_dates_later(v_srcroot, v_omitted_later);
            IF NOT v_omitted_later THEN
                v_out_obj.put('Later', v_result_later);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('later') THEN
                    v_errors('later') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_earlier VARCHAR2(4000 CHAR);
            v_omitted_earlier BOOLEAN;
        BEGIN
            v_result_earlier := fn_builtins_dates_earlier(v_srcroot, v_omitted_earlier);
            IF NOT v_omitted_earlier THEN
                v_out_obj.put('Earlier', v_result_earlier);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('earlier') THEN
                    v_errors('earlier') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_last_part VARCHAR2(4000 CHAR);
            v_omitted_last_part BOOLEAN;
        BEGIN
            v_result_last_part := fn_builtins_dates_last_part(v_srcroot, v_omitted_last_part);
            IF NOT v_omitted_last_part THEN
                v_out_obj.put('LastPart', v_result_last_part);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('last_part') THEN
                    v_errors('last_part') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_tags VARCHAR2(4000 CHAR);
            v_omitted_tags BOOLEAN;
        BEGIN
            v_result_tags := fn_builtins_dates_tags(v_srcroot, v_omitted_tags);
            IF NOT v_omitted_tags THEN
                v_out_obj.put('Tags', v_result_tags);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('tags') THEN
                    v_errors('tags') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_glued VARCHAR2(4000 CHAR);
            v_omitted_glued BOOLEAN;
        BEGIN
            v_result_glued := fn_builtins_dates_glued(v_srcroot, v_omitted_glued);
            IF NOT v_omitted_glued THEN
                v_out_obj.put('Glued', v_result_glued);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('glued') THEN
                    v_errors('glued') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ok_ids VARCHAR2(4000 CHAR);
            v_omitted_ok_ids BOOLEAN;
        BEGIN
            v_result_ok_ids := fn_builtins_dates_ok_ids(v_srcroot, v_omitted_ok_ids);
            IF NOT v_omitted_ok_ids THEN
                v_out_obj.put('OkIds', v_result_ok_ids);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ok_ids') THEN
                    v_errors('ok_ids') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_custom VARCHAR2(4000 CHAR);
            v_omitted_custom BOOLEAN;
        BEGIN
            v_result_custom := fn_builtins_dates_custom(v_srcroot, v_omitted_custom);
            IF NOT v_omitted_custom THEN
                v_out_obj.put('Custom', v_result_custom);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('custom') THEN
                    v_errors('custom') := SQLERRM;
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
    END map_builtins_dates_safe;
END J2JME_MAP_BUILTINS_DATES;
/
