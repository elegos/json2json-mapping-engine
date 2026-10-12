CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_BUILTINS_MORE AS
    PROCEDURE map_builtins_more (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_more_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_BUILTINS_MORE;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_BUILTINS_MORE AS
    FUNCTION fn_builtins_more_upper_name(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_upper_name__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_upper_name__ret := COALESCE(UPPER(p_root.get_String('name')), '~');
        IF v_upper_name__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_upper_name__ret;
    END fn_builtins_more_upper_name;

    FUNCTION fn_builtins_more_lower_name(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_lower_name__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_lower_name__ret := COALESCE(LOWER(p_root.get_String('name')), '~');
        IF v_lower_name__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_lower_name__ret;
    END fn_builtins_more_lower_name;

    FUNCTION fn_builtins_more_trimmed(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_trimmed__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_trimmed__ret := COALESCE(TRIM(p_root.get_String('name')), '~');
        IF v_trimmed__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_trimmed__ret;
    END fn_builtins_more_trimmed;

    FUNCTION fn_builtins_more_code_length(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_code_length__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_code_length__ret := COALESCE(LENGTH(p_root.get_String('code')), (0 - 1));
        IF v_code_length__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_code_length__ret;
    END fn_builtins_more_code_length;

    FUNCTION fn_builtins_more_sub(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_sub__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_sub__ret := COALESCE(SUBSTR(p_root.get_String('code'), GREATEST(4, 1), 2), '~');
        IF v_sub__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_sub__ret;
    END fn_builtins_more_sub;

    FUNCTION fn_builtins_more_sub_rest(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_sub_rest__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_sub_rest__ret := COALESCE(SUBSTR(p_root.get_String('code'), GREATEST(4, 1)), '~');
        IF v_sub_rest__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_sub_rest__ret;
    END fn_builtins_more_sub_rest;

    FUNCTION fn_builtins_more_sub_zero(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_sub_zero__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_sub_zero__ret := COALESCE(SUBSTR(p_root.get_String('code'), GREATEST(0, 1), 2), '~');
        IF v_sub_zero__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_sub_zero__ret;
    END fn_builtins_more_sub_zero;

    FUNCTION fn_builtins_more_first3(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_first3__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_first3__ret := COALESCE(SUBSTR(p_root.get_String('code'), 1, 3), '~');
        IF v_first3__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_first3__ret;
    END fn_builtins_more_first3;

    FUNCTION fn_builtins_more_last3(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_last3__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_last3__ret := COALESCE((CASE WHEN 3 < 1 THEN NULL ELSE SUBSTR(p_root.get_String('code'), GREATEST(LENGTH(p_root.get_String('code')) - 3 + 1, 1)) END), '~');
        IF v_last3__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_last3__ret;
    END fn_builtins_more_last3;

    FUNCTION fn_builtins_more_left_long(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_left_long__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_left_long__ret := COALESCE(SUBSTR(p_root.get_String('code'), 1, 20), '~');
        IF v_left_long__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_left_long__ret;
    END fn_builtins_more_left_long;

    FUNCTION fn_builtins_more_right_long(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_right_long__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_right_long__ret := COALESCE((CASE WHEN 20 < 1 THEN NULL ELSE SUBSTR(p_root.get_String('code'), GREATEST(LENGTH(p_root.get_String('code')) - 20 + 1, 1)) END), '~');
        IF v_right_long__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_right_long__ret;
    END fn_builtins_more_right_long;

    FUNCTION fn_builtins_more_pad_zero(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_pad_zero__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_pad_zero__ret := COALESCE((CASE WHEN LENGTH(MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('seq'))) >= 5 THEN MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('seq')) ELSE LPAD(MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('seq')), 5, '0') END), '~');
        IF v_pad_zero__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_pad_zero__ret;
    END fn_builtins_more_pad_zero;

    FUNCTION fn_builtins_more_pad_long(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_pad_long__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_pad_long__ret := COALESCE((CASE WHEN LENGTH(p_root.get_String('code')) >= 3 THEN p_root.get_String('code') ELSE LPAD(p_root.get_String('code'), 3, '0') END), '~');
        IF v_pad_long__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_pad_long__ret;
    END fn_builtins_more_pad_long;

    FUNCTION fn_builtins_more_pad_right_dots(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_pad_right_dots__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_pad_right_dots__ret := COALESCE((CASE WHEN LENGTH(p_root.get_String('code')) >= 10 THEN p_root.get_String('code') ELSE RPAD(p_root.get_String('code'), 10, '.') END), '~');
        IF v_pad_right_dots__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_pad_right_dots__ret;
    END fn_builtins_more_pad_right_dots;

    FUNCTION fn_builtins_more_has_dash(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN BOOLEAN IS
        v_has_dash__ret BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_has_dash__ret := (CASE WHEN INSTR(p_root.get_String('code'), '-') > 0 THEN TRUE ELSE FALSE END);
        IF v_has_dash__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_has_dash__ret;
    END fn_builtins_more_has_dash;

    FUNCTION fn_builtins_more_starts_ab(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN BOOLEAN IS
        v_starts_ab__ret BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_starts_ab__ret := (CASE WHEN SUBSTR(p_root.get_String('code'), 1, LENGTH('ab')) = 'ab' THEN TRUE ELSE FALSE END);
        IF v_starts_ab__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_starts_ab__ret;
    END fn_builtins_more_starts_ab;

    FUNCTION fn_builtins_more_ends_ab(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN BOOLEAN IS
        v_ends_ab__ret BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_ends_ab__ret := (CASE WHEN SUBSTR(p_root.get_String('code'), -LENGTH('ab')) = 'ab' THEN TRUE ELSE FALSE END);
        IF v_ends_ab__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ends_ab__ret;
    END fn_builtins_more_ends_ab;

    FUNCTION fn_builtins_more_empty_part(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN BOOLEAN IS
        v_empty_part__ret BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_empty_part__ret := (CASE WHEN INSTR(p_root.get_String('code'), '') > 0 THEN TRUE ELSE FALSE END);
        IF v_empty_part__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_empty_part__ret;
    END fn_builtins_more_empty_part;

    FUNCTION fn_builtins_more_absolute(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_absolute__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_absolute__ret := ABS(p_root.get_Number('n'));
        IF v_absolute__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_absolute__ret;
    END fn_builtins_more_absolute;

    FUNCTION fn_builtins_more_floored(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_floored__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_floored__ret := FLOOR(p_root.get_Number('n'));
        IF v_floored__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_floored__ret;
    END fn_builtins_more_floored;

    FUNCTION fn_builtins_more_ceiled(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_ceiled__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_ceiled__ret := CEIL(p_root.get_Number('n'));
        IF v_ceiled__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_ceiled__ret;
    END fn_builtins_more_ceiled;

    FUNCTION fn_builtins_more_date_eu(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_date_eu__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_date_eu__ret := COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.format_date(p_root.get_String('date'), 'DD/MM/YYYY'), '~');
        IF v_date_eu__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_date_eu__ret;
    END fn_builtins_more_date_eu;

    FUNCTION fn_builtins_more_date_time(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_date_time__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_date_time__ret := COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.format_date(p_root.get_String('dt'), 'YYYY-MM-DD HH24:MI:SS'), '~');
        IF v_date_time__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_date_time__ret;
    END fn_builtins_more_date_time;

    FUNCTION fn_builtins_more_date_only_time(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_date_only_time__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_date_only_time__ret := COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.format_date(p_root.get_String('date'), 'HH24:MI'), '~');
        IF v_date_only_time__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_date_only_time__ret;
    END fn_builtins_more_date_only_time;

    FUNCTION fn_builtins_more_custom(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_custom__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_custom__ret := COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.format_date(p_root.get_String('date'), p_root.get_String('fmt')), '~');
        IF v_custom__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_custom__ret;
    END fn_builtins_more_custom;

    PROCEDURE map_builtins_more (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_upper_name VARCHAR2(4000 CHAR);
            v_omitted_upper_name BOOLEAN;
        BEGIN
            v_result_upper_name := fn_builtins_more_upper_name(v_srcroot, v_omitted_upper_name);
            IF NOT v_omitted_upper_name THEN
                v_out_obj.put('Upper', v_result_upper_name);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('upper_name') THEN
                    v_errors('upper_name') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_lower_name VARCHAR2(4000 CHAR);
            v_omitted_lower_name BOOLEAN;
        BEGIN
            v_result_lower_name := fn_builtins_more_lower_name(v_srcroot, v_omitted_lower_name);
            IF NOT v_omitted_lower_name THEN
                v_out_obj.put('Lower', v_result_lower_name);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('lower_name') THEN
                    v_errors('lower_name') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_trimmed VARCHAR2(4000 CHAR);
            v_omitted_trimmed BOOLEAN;
        BEGIN
            v_result_trimmed := fn_builtins_more_trimmed(v_srcroot, v_omitted_trimmed);
            IF NOT v_omitted_trimmed THEN
                v_out_obj.put('Trimmed', v_result_trimmed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('trimmed') THEN
                    v_errors('trimmed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_code_length NUMBER;
            v_omitted_code_length BOOLEAN;
        BEGIN
            v_result_code_length := fn_builtins_more_code_length(v_srcroot, v_omitted_code_length);
            IF NOT v_omitted_code_length THEN
                v_out_obj.put('Length', v_result_code_length);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('code_length') THEN
                    v_errors('code_length') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_sub VARCHAR2(4000 CHAR);
            v_omitted_sub BOOLEAN;
        BEGIN
            v_result_sub := fn_builtins_more_sub(v_srcroot, v_omitted_sub);
            IF NOT v_omitted_sub THEN
                v_out_obj.put('Sub', v_result_sub);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('sub') THEN
                    v_errors('sub') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_sub_rest VARCHAR2(4000 CHAR);
            v_omitted_sub_rest BOOLEAN;
        BEGIN
            v_result_sub_rest := fn_builtins_more_sub_rest(v_srcroot, v_omitted_sub_rest);
            IF NOT v_omitted_sub_rest THEN
                v_out_obj.put('SubRest', v_result_sub_rest);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('sub_rest') THEN
                    v_errors('sub_rest') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_sub_zero VARCHAR2(4000 CHAR);
            v_omitted_sub_zero BOOLEAN;
        BEGIN
            v_result_sub_zero := fn_builtins_more_sub_zero(v_srcroot, v_omitted_sub_zero);
            IF NOT v_omitted_sub_zero THEN
                v_out_obj.put('SubZero', v_result_sub_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('sub_zero') THEN
                    v_errors('sub_zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first3 VARCHAR2(4000 CHAR);
            v_omitted_first3 BOOLEAN;
        BEGIN
            v_result_first3 := fn_builtins_more_first3(v_srcroot, v_omitted_first3);
            IF NOT v_omitted_first3 THEN
                v_out_obj.put('First3', v_result_first3);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first3') THEN
                    v_errors('first3') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_last3 VARCHAR2(4000 CHAR);
            v_omitted_last3 BOOLEAN;
        BEGIN
            v_result_last3 := fn_builtins_more_last3(v_srcroot, v_omitted_last3);
            IF NOT v_omitted_last3 THEN
                v_out_obj.put('Last3', v_result_last3);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('last3') THEN
                    v_errors('last3') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_left_long VARCHAR2(4000 CHAR);
            v_omitted_left_long BOOLEAN;
        BEGIN
            v_result_left_long := fn_builtins_more_left_long(v_srcroot, v_omitted_left_long);
            IF NOT v_omitted_left_long THEN
                v_out_obj.put('LeftLong', v_result_left_long);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('left_long') THEN
                    v_errors('left_long') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_right_long VARCHAR2(4000 CHAR);
            v_omitted_right_long BOOLEAN;
        BEGIN
            v_result_right_long := fn_builtins_more_right_long(v_srcroot, v_omitted_right_long);
            IF NOT v_omitted_right_long THEN
                v_out_obj.put('RightLong', v_result_right_long);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('right_long') THEN
                    v_errors('right_long') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_pad_zero VARCHAR2(4000 CHAR);
            v_omitted_pad_zero BOOLEAN;
        BEGIN
            v_result_pad_zero := fn_builtins_more_pad_zero(v_srcroot, v_omitted_pad_zero);
            IF NOT v_omitted_pad_zero THEN
                v_out_obj.put('PadZero', v_result_pad_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('pad_zero') THEN
                    v_errors('pad_zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_pad_long VARCHAR2(4000 CHAR);
            v_omitted_pad_long BOOLEAN;
        BEGIN
            v_result_pad_long := fn_builtins_more_pad_long(v_srcroot, v_omitted_pad_long);
            IF NOT v_omitted_pad_long THEN
                v_out_obj.put('PadLong', v_result_pad_long);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('pad_long') THEN
                    v_errors('pad_long') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_pad_right_dots VARCHAR2(4000 CHAR);
            v_omitted_pad_right_dots BOOLEAN;
        BEGIN
            v_result_pad_right_dots := fn_builtins_more_pad_right_dots(v_srcroot, v_omitted_pad_right_dots);
            IF NOT v_omitted_pad_right_dots THEN
                v_out_obj.put('PadRight', v_result_pad_right_dots);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('pad_right_dots') THEN
                    v_errors('pad_right_dots') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_has_dash BOOLEAN;
            v_omitted_has_dash BOOLEAN;
        BEGIN
            v_result_has_dash := fn_builtins_more_has_dash(v_srcroot, v_omitted_has_dash);
            IF NOT v_omitted_has_dash THEN
                v_out_obj.put('HasDash', v_result_has_dash);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('has_dash') THEN
                    v_errors('has_dash') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_starts_ab BOOLEAN;
            v_omitted_starts_ab BOOLEAN;
        BEGIN
            v_result_starts_ab := fn_builtins_more_starts_ab(v_srcroot, v_omitted_starts_ab);
            IF NOT v_omitted_starts_ab THEN
                v_out_obj.put('StartsAb', v_result_starts_ab);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('starts_ab') THEN
                    v_errors('starts_ab') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ends_ab BOOLEAN;
            v_omitted_ends_ab BOOLEAN;
        BEGIN
            v_result_ends_ab := fn_builtins_more_ends_ab(v_srcroot, v_omitted_ends_ab);
            IF NOT v_omitted_ends_ab THEN
                v_out_obj.put('EndsAb', v_result_ends_ab);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ends_ab') THEN
                    v_errors('ends_ab') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_part BOOLEAN;
            v_omitted_empty_part BOOLEAN;
        BEGIN
            v_result_empty_part := fn_builtins_more_empty_part(v_srcroot, v_omitted_empty_part);
            IF NOT v_omitted_empty_part THEN
                v_out_obj.put('EmptyPart', v_result_empty_part);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_part') THEN
                    v_errors('empty_part') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_absolute NUMBER;
            v_omitted_absolute BOOLEAN;
        BEGIN
            v_result_absolute := fn_builtins_more_absolute(v_srcroot, v_omitted_absolute);
            IF NOT v_omitted_absolute THEN
                v_out_obj.put('Abs', v_result_absolute);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('absolute') THEN
                    v_errors('absolute') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_floored NUMBER;
            v_omitted_floored BOOLEAN;
        BEGIN
            v_result_floored := fn_builtins_more_floored(v_srcroot, v_omitted_floored);
            IF NOT v_omitted_floored THEN
                v_out_obj.put('Floor', v_result_floored);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('floored') THEN
                    v_errors('floored') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ceiled NUMBER;
            v_omitted_ceiled BOOLEAN;
        BEGIN
            v_result_ceiled := fn_builtins_more_ceiled(v_srcroot, v_omitted_ceiled);
            IF NOT v_omitted_ceiled THEN
                v_out_obj.put('Ceil', v_result_ceiled);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ceiled') THEN
                    v_errors('ceiled') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_date_eu VARCHAR2(4000 CHAR);
            v_omitted_date_eu BOOLEAN;
        BEGIN
            v_result_date_eu := fn_builtins_more_date_eu(v_srcroot, v_omitted_date_eu);
            IF NOT v_omitted_date_eu THEN
                v_out_obj.put('DateEu', v_result_date_eu);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('date_eu') THEN
                    v_errors('date_eu') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_date_time VARCHAR2(4000 CHAR);
            v_omitted_date_time BOOLEAN;
        BEGIN
            v_result_date_time := fn_builtins_more_date_time(v_srcroot, v_omitted_date_time);
            IF NOT v_omitted_date_time THEN
                v_out_obj.put('DateTime', v_result_date_time);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('date_time') THEN
                    v_errors('date_time') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_date_only_time VARCHAR2(4000 CHAR);
            v_omitted_date_only_time BOOLEAN;
        BEGIN
            v_result_date_only_time := fn_builtins_more_date_only_time(v_srcroot, v_omitted_date_only_time);
            IF NOT v_omitted_date_only_time THEN
                v_out_obj.put('DateOnlyTime', v_result_date_only_time);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('date_only_time') THEN
                    v_errors('date_only_time') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_custom VARCHAR2(4000 CHAR);
            v_omitted_custom BOOLEAN;
        BEGIN
            v_result_custom := fn_builtins_more_custom(v_srcroot, v_omitted_custom);
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
                v_payload.put('mapping', 'builtins_more');
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
                v_payload.put('mapping', 'builtins_more');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_builtins_more;

    PROCEDURE map_builtins_more_safe (
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
            v_result_upper_name VARCHAR2(4000 CHAR);
            v_omitted_upper_name BOOLEAN;
        BEGIN
            v_result_upper_name := fn_builtins_more_upper_name(v_srcroot, v_omitted_upper_name);
            IF NOT v_omitted_upper_name THEN
                v_out_obj.put('Upper', v_result_upper_name);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('upper_name') THEN
                    v_errors('upper_name') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_lower_name VARCHAR2(4000 CHAR);
            v_omitted_lower_name BOOLEAN;
        BEGIN
            v_result_lower_name := fn_builtins_more_lower_name(v_srcroot, v_omitted_lower_name);
            IF NOT v_omitted_lower_name THEN
                v_out_obj.put('Lower', v_result_lower_name);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('lower_name') THEN
                    v_errors('lower_name') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_trimmed VARCHAR2(4000 CHAR);
            v_omitted_trimmed BOOLEAN;
        BEGIN
            v_result_trimmed := fn_builtins_more_trimmed(v_srcroot, v_omitted_trimmed);
            IF NOT v_omitted_trimmed THEN
                v_out_obj.put('Trimmed', v_result_trimmed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('trimmed') THEN
                    v_errors('trimmed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_code_length NUMBER;
            v_omitted_code_length BOOLEAN;
        BEGIN
            v_result_code_length := fn_builtins_more_code_length(v_srcroot, v_omitted_code_length);
            IF NOT v_omitted_code_length THEN
                v_out_obj.put('Length', v_result_code_length);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('code_length') THEN
                    v_errors('code_length') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_sub VARCHAR2(4000 CHAR);
            v_omitted_sub BOOLEAN;
        BEGIN
            v_result_sub := fn_builtins_more_sub(v_srcroot, v_omitted_sub);
            IF NOT v_omitted_sub THEN
                v_out_obj.put('Sub', v_result_sub);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('sub') THEN
                    v_errors('sub') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_sub_rest VARCHAR2(4000 CHAR);
            v_omitted_sub_rest BOOLEAN;
        BEGIN
            v_result_sub_rest := fn_builtins_more_sub_rest(v_srcroot, v_omitted_sub_rest);
            IF NOT v_omitted_sub_rest THEN
                v_out_obj.put('SubRest', v_result_sub_rest);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('sub_rest') THEN
                    v_errors('sub_rest') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_sub_zero VARCHAR2(4000 CHAR);
            v_omitted_sub_zero BOOLEAN;
        BEGIN
            v_result_sub_zero := fn_builtins_more_sub_zero(v_srcroot, v_omitted_sub_zero);
            IF NOT v_omitted_sub_zero THEN
                v_out_obj.put('SubZero', v_result_sub_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('sub_zero') THEN
                    v_errors('sub_zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first3 VARCHAR2(4000 CHAR);
            v_omitted_first3 BOOLEAN;
        BEGIN
            v_result_first3 := fn_builtins_more_first3(v_srcroot, v_omitted_first3);
            IF NOT v_omitted_first3 THEN
                v_out_obj.put('First3', v_result_first3);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first3') THEN
                    v_errors('first3') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_last3 VARCHAR2(4000 CHAR);
            v_omitted_last3 BOOLEAN;
        BEGIN
            v_result_last3 := fn_builtins_more_last3(v_srcroot, v_omitted_last3);
            IF NOT v_omitted_last3 THEN
                v_out_obj.put('Last3', v_result_last3);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('last3') THEN
                    v_errors('last3') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_left_long VARCHAR2(4000 CHAR);
            v_omitted_left_long BOOLEAN;
        BEGIN
            v_result_left_long := fn_builtins_more_left_long(v_srcroot, v_omitted_left_long);
            IF NOT v_omitted_left_long THEN
                v_out_obj.put('LeftLong', v_result_left_long);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('left_long') THEN
                    v_errors('left_long') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_right_long VARCHAR2(4000 CHAR);
            v_omitted_right_long BOOLEAN;
        BEGIN
            v_result_right_long := fn_builtins_more_right_long(v_srcroot, v_omitted_right_long);
            IF NOT v_omitted_right_long THEN
                v_out_obj.put('RightLong', v_result_right_long);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('right_long') THEN
                    v_errors('right_long') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_pad_zero VARCHAR2(4000 CHAR);
            v_omitted_pad_zero BOOLEAN;
        BEGIN
            v_result_pad_zero := fn_builtins_more_pad_zero(v_srcroot, v_omitted_pad_zero);
            IF NOT v_omitted_pad_zero THEN
                v_out_obj.put('PadZero', v_result_pad_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('pad_zero') THEN
                    v_errors('pad_zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_pad_long VARCHAR2(4000 CHAR);
            v_omitted_pad_long BOOLEAN;
        BEGIN
            v_result_pad_long := fn_builtins_more_pad_long(v_srcroot, v_omitted_pad_long);
            IF NOT v_omitted_pad_long THEN
                v_out_obj.put('PadLong', v_result_pad_long);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('pad_long') THEN
                    v_errors('pad_long') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_pad_right_dots VARCHAR2(4000 CHAR);
            v_omitted_pad_right_dots BOOLEAN;
        BEGIN
            v_result_pad_right_dots := fn_builtins_more_pad_right_dots(v_srcroot, v_omitted_pad_right_dots);
            IF NOT v_omitted_pad_right_dots THEN
                v_out_obj.put('PadRight', v_result_pad_right_dots);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('pad_right_dots') THEN
                    v_errors('pad_right_dots') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_has_dash BOOLEAN;
            v_omitted_has_dash BOOLEAN;
        BEGIN
            v_result_has_dash := fn_builtins_more_has_dash(v_srcroot, v_omitted_has_dash);
            IF NOT v_omitted_has_dash THEN
                v_out_obj.put('HasDash', v_result_has_dash);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('has_dash') THEN
                    v_errors('has_dash') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_starts_ab BOOLEAN;
            v_omitted_starts_ab BOOLEAN;
        BEGIN
            v_result_starts_ab := fn_builtins_more_starts_ab(v_srcroot, v_omitted_starts_ab);
            IF NOT v_omitted_starts_ab THEN
                v_out_obj.put('StartsAb', v_result_starts_ab);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('starts_ab') THEN
                    v_errors('starts_ab') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ends_ab BOOLEAN;
            v_omitted_ends_ab BOOLEAN;
        BEGIN
            v_result_ends_ab := fn_builtins_more_ends_ab(v_srcroot, v_omitted_ends_ab);
            IF NOT v_omitted_ends_ab THEN
                v_out_obj.put('EndsAb', v_result_ends_ab);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ends_ab') THEN
                    v_errors('ends_ab') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_part BOOLEAN;
            v_omitted_empty_part BOOLEAN;
        BEGIN
            v_result_empty_part := fn_builtins_more_empty_part(v_srcroot, v_omitted_empty_part);
            IF NOT v_omitted_empty_part THEN
                v_out_obj.put('EmptyPart', v_result_empty_part);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_part') THEN
                    v_errors('empty_part') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_absolute NUMBER;
            v_omitted_absolute BOOLEAN;
        BEGIN
            v_result_absolute := fn_builtins_more_absolute(v_srcroot, v_omitted_absolute);
            IF NOT v_omitted_absolute THEN
                v_out_obj.put('Abs', v_result_absolute);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('absolute') THEN
                    v_errors('absolute') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_floored NUMBER;
            v_omitted_floored BOOLEAN;
        BEGIN
            v_result_floored := fn_builtins_more_floored(v_srcroot, v_omitted_floored);
            IF NOT v_omitted_floored THEN
                v_out_obj.put('Floor', v_result_floored);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('floored') THEN
                    v_errors('floored') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ceiled NUMBER;
            v_omitted_ceiled BOOLEAN;
        BEGIN
            v_result_ceiled := fn_builtins_more_ceiled(v_srcroot, v_omitted_ceiled);
            IF NOT v_omitted_ceiled THEN
                v_out_obj.put('Ceil', v_result_ceiled);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ceiled') THEN
                    v_errors('ceiled') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_date_eu VARCHAR2(4000 CHAR);
            v_omitted_date_eu BOOLEAN;
        BEGIN
            v_result_date_eu := fn_builtins_more_date_eu(v_srcroot, v_omitted_date_eu);
            IF NOT v_omitted_date_eu THEN
                v_out_obj.put('DateEu', v_result_date_eu);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('date_eu') THEN
                    v_errors('date_eu') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_date_time VARCHAR2(4000 CHAR);
            v_omitted_date_time BOOLEAN;
        BEGIN
            v_result_date_time := fn_builtins_more_date_time(v_srcroot, v_omitted_date_time);
            IF NOT v_omitted_date_time THEN
                v_out_obj.put('DateTime', v_result_date_time);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('date_time') THEN
                    v_errors('date_time') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_date_only_time VARCHAR2(4000 CHAR);
            v_omitted_date_only_time BOOLEAN;
        BEGIN
            v_result_date_only_time := fn_builtins_more_date_only_time(v_srcroot, v_omitted_date_only_time);
            IF NOT v_omitted_date_only_time THEN
                v_out_obj.put('DateOnlyTime', v_result_date_only_time);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('date_only_time') THEN
                    v_errors('date_only_time') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_custom VARCHAR2(4000 CHAR);
            v_omitted_custom BOOLEAN;
        BEGIN
            v_result_custom := fn_builtins_more_custom(v_srcroot, v_omitted_custom);
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
    END map_builtins_more_safe;
END J2JME_MAP_BUILTINS_MORE;
/
