CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_BUILTINS_TEXT AS
    PROCEDURE map_builtins_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_BUILTINS_TEXT;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_BUILTINS_TEXT AS
    FUNCTION fn_builtins_text_replaced(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN REPLACE(p_root.get_String('s'), '-', '+');
    END fn_builtins_text_replaced;

    FUNCTION fn_builtins_text_removed(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN REPLACE(p_root.get_String('s'), '-');
    END fn_builtins_text_removed;

    FUNCTION fn_builtins_text_prefix(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.remove_prefix(p_root.get_String('code'), 'ID-');
    END fn_builtins_text_prefix;

    FUNCTION fn_builtins_text_prefix_absent(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.remove_prefix(p_root.get_String('s'), 'ID-');
    END fn_builtins_text_prefix_absent;

    FUNCTION fn_builtins_text_digits(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN REGEXP_REPLACE(p_root.get_String('phone'), '[^0-9]', '');
    END fn_builtins_text_digits;

    FUNCTION fn_builtins_text_swapped(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN REGEXP_REPLACE(p_root.get_String('ref'), '([a-z]+)-([0-9]+)/([0-9]+)', '\3-\2');
    END fn_builtins_text_swapped;

    FUNCTION fn_builtins_text_group(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN REGEXP_SUBSTR(p_root.get_String('ref'), '([a-z]+)-([0-9]+)', 1, 1, NULL, 2);
    END fn_builtins_text_group;

    FUNCTION fn_builtins_text_whole(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN REGEXP_SUBSTR(p_root.get_String('ref'), '[0-9]+', 1, 1, NULL, 0);
    END fn_builtins_text_whole;

    FUNCTION fn_builtins_text_no_group(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(REGEXP_SUBSTR(p_root.get_String('s'), '[0-9]+', 1, 1, NULL, 0), 'none');
    END fn_builtins_text_no_group;

    FUNCTION fn_builtins_text_fixed(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.format_decimal(p_root.get_Number('n'), 2);
    END fn_builtins_text_fixed;

    FUNCTION fn_builtins_text_fixed_rounded(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.format_decimal(p_root.get_Number('big'), 2);
    END fn_builtins_text_fixed_rounded;

    FUNCTION fn_builtins_text_fixed_whole(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.format_decimal(p_root.get_Number('whole'), 0);
    END fn_builtins_text_fixed_whole;

    FUNCTION fn_builtins_text_fixed_negative(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.format_decimal(p_root.get_Number('neg'), 1);
    END fn_builtins_text_fixed_negative;

    FUNCTION fn_builtins_text_rounded(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN ROUND(p_root.get_Number('n'));
    END fn_builtins_text_rounded;

    FUNCTION fn_builtins_text_number_from_text(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_number(p_root.get('num_text'));
    END fn_builtins_text_number_from_text;

    FUNCTION fn_builtins_text_decimal_from_text(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_number(p_root.get('dec_text'));
    END fn_builtins_text_decimal_from_text;

    FUNCTION fn_builtins_text_number_from_number(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_number(p_root.get('n'));
    END fn_builtins_text_number_from_number;

    FUNCTION fn_builtins_text_number_from_expr(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN TO_NUMBER(TRIM(MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('pair'), ',', 2)), '99999999999999999999999999999999D99999999999999999999', 'NLS_NUMERIC_CHARACTERS=''.,''');
    END fn_builtins_text_number_from_expr;

    FUNCTION fn_builtins_text_text_from_number(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('n'));
    END fn_builtins_text_text_from_number;

    FUNCTION fn_builtins_text_text_from_whole(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('whole'));
    END fn_builtins_text_text_from_whole;

    FUNCTION fn_builtins_text_text_from_small(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('small'));
    END fn_builtins_text_text_from_small;

    FUNCTION fn_builtins_text_text_from_text(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('s'));
    END fn_builtins_text_text_from_text;

    FUNCTION fn_builtins_text_text_from_bool(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('flag'));
    END fn_builtins_text_text_from_bool;

    FUNCTION fn_builtins_text_text_from_list(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_string(p_root.get('list'));
    END fn_builtins_text_text_from_list;

    FUNCTION fn_builtins_text_text_from_expr(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN TO_CHAR(ROUND(p_root.get_Number('n'), 0), 'TM9', 'NLS_NUMERIC_CHARACTERS=''.,''');
    END fn_builtins_text_text_from_expr;

    FUNCTION fn_builtins_text_text_from_concat(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN ('a' || 'b');
    END fn_builtins_text_text_from_concat;

    FUNCTION fn_builtins_text_utc(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_utc(p_root.get_String('ts'));
    END fn_builtins_text_utc;

    FUNCTION fn_builtins_text_utc_fraction(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_utc(p_root.get_String('ts_frac'));
    END fn_builtins_text_utc_fraction;

    FUNCTION fn_builtins_text_utc_from_z(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_utc(p_root.get_String('ts_z'));
    END fn_builtins_text_utc_from_z;

    FUNCTION fn_builtins_text_utc_naive(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.to_utc(p_root.get_String('ts_naive'));
    END fn_builtins_text_utc_naive;

    FUNCTION fn_builtins_text_rfc(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.rfc3339_normalize(p_root.get_String('ts'));
    END fn_builtins_text_rfc;

    FUNCTION fn_builtins_text_rfc_naive(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.rfc3339_normalize(p_root.get_String('ts_naive'));
    END fn_builtins_text_rfc_naive;

    FUNCTION fn_builtins_text_rfc_zero(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.rfc3339_normalize(p_root.get_String('ts_zero'));
    END fn_builtins_text_rfc_zero;

    PROCEDURE map_builtins_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_replaced VARCHAR2(4000 CHAR);
            v_omitted_replaced BOOLEAN;
        BEGIN
            v_result_replaced := fn_builtins_text_replaced(v_srcroot, v_omitted_replaced);
            IF NOT v_omitted_replaced THEN
                v_out_obj.put('Replaced', v_result_replaced);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('replaced') THEN
                    v_errors('replaced') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_removed VARCHAR2(4000 CHAR);
            v_omitted_removed BOOLEAN;
        BEGIN
            v_result_removed := fn_builtins_text_removed(v_srcroot, v_omitted_removed);
            IF NOT v_omitted_removed THEN
                v_out_obj.put('Removed', v_result_removed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('removed') THEN
                    v_errors('removed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_prefix VARCHAR2(4000 CHAR);
            v_omitted_prefix BOOLEAN;
        BEGIN
            v_result_prefix := fn_builtins_text_prefix(v_srcroot, v_omitted_prefix);
            IF NOT v_omitted_prefix THEN
                v_out_obj.put('Prefix', v_result_prefix);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('prefix') THEN
                    v_errors('prefix') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_prefix_absent VARCHAR2(4000 CHAR);
            v_omitted_prefix_absent BOOLEAN;
        BEGIN
            v_result_prefix_absent := fn_builtins_text_prefix_absent(v_srcroot, v_omitted_prefix_absent);
            IF NOT v_omitted_prefix_absent THEN
                v_out_obj.put('PrefixAbsent', v_result_prefix_absent);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('prefix_absent') THEN
                    v_errors('prefix_absent') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_digits VARCHAR2(4000 CHAR);
            v_omitted_digits BOOLEAN;
        BEGIN
            v_result_digits := fn_builtins_text_digits(v_srcroot, v_omitted_digits);
            IF NOT v_omitted_digits THEN
                v_out_obj.put('Digits', v_result_digits);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('digits') THEN
                    v_errors('digits') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_swapped VARCHAR2(4000 CHAR);
            v_omitted_swapped BOOLEAN;
        BEGIN
            v_result_swapped := fn_builtins_text_swapped(v_srcroot, v_omitted_swapped);
            IF NOT v_omitted_swapped THEN
                v_out_obj.put('Swapped', v_result_swapped);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('swapped') THEN
                    v_errors('swapped') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_group VARCHAR2(4000 CHAR);
            v_omitted_group BOOLEAN;
        BEGIN
            v_result_group := fn_builtins_text_group(v_srcroot, v_omitted_group);
            IF NOT v_omitted_group THEN
                v_out_obj.put('Group', v_result_group);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('group') THEN
                    v_errors('group') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_whole VARCHAR2(4000 CHAR);
            v_omitted_whole BOOLEAN;
        BEGIN
            v_result_whole := fn_builtins_text_whole(v_srcroot, v_omitted_whole);
            IF NOT v_omitted_whole THEN
                v_out_obj.put('Whole', v_result_whole);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('whole') THEN
                    v_errors('whole') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_no_group VARCHAR2(4000 CHAR);
            v_omitted_no_group BOOLEAN;
        BEGIN
            v_result_no_group := fn_builtins_text_no_group(v_srcroot, v_omitted_no_group);
            IF NOT v_omitted_no_group THEN
                v_out_obj.put('NoGroup', v_result_no_group);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('no_group') THEN
                    v_errors('no_group') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed VARCHAR2(4000 CHAR);
            v_omitted_fixed BOOLEAN;
        BEGIN
            v_result_fixed := fn_builtins_text_fixed(v_srcroot, v_omitted_fixed);
            IF NOT v_omitted_fixed THEN
                v_out_obj.put('Fixed', v_result_fixed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed') THEN
                    v_errors('fixed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed_rounded VARCHAR2(4000 CHAR);
            v_omitted_fixed_rounded BOOLEAN;
        BEGIN
            v_result_fixed_rounded := fn_builtins_text_fixed_rounded(v_srcroot, v_omitted_fixed_rounded);
            IF NOT v_omitted_fixed_rounded THEN
                v_out_obj.put('FixedRounded', v_result_fixed_rounded);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed_rounded') THEN
                    v_errors('fixed_rounded') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed_whole VARCHAR2(4000 CHAR);
            v_omitted_fixed_whole BOOLEAN;
        BEGIN
            v_result_fixed_whole := fn_builtins_text_fixed_whole(v_srcroot, v_omitted_fixed_whole);
            IF NOT v_omitted_fixed_whole THEN
                v_out_obj.put('FixedWhole', v_result_fixed_whole);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed_whole') THEN
                    v_errors('fixed_whole') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed_negative VARCHAR2(4000 CHAR);
            v_omitted_fixed_negative BOOLEAN;
        BEGIN
            v_result_fixed_negative := fn_builtins_text_fixed_negative(v_srcroot, v_omitted_fixed_negative);
            IF NOT v_omitted_fixed_negative THEN
                v_out_obj.put('FixedNegative', v_result_fixed_negative);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed_negative') THEN
                    v_errors('fixed_negative') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rounded NUMBER;
            v_omitted_rounded BOOLEAN;
        BEGIN
            v_result_rounded := fn_builtins_text_rounded(v_srcroot, v_omitted_rounded);
            IF NOT v_omitted_rounded THEN
                v_out_obj.put('Rounded', v_result_rounded);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rounded') THEN
                    v_errors('rounded') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_from_text NUMBER;
            v_omitted_number_from_text BOOLEAN;
        BEGIN
            v_result_number_from_text := fn_builtins_text_number_from_text(v_srcroot, v_omitted_number_from_text);
            IF NOT v_omitted_number_from_text THEN
                v_out_obj.put('NumberFromText', v_result_number_from_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_from_text') THEN
                    v_errors('number_from_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_decimal_from_text NUMBER;
            v_omitted_decimal_from_text BOOLEAN;
        BEGIN
            v_result_decimal_from_text := fn_builtins_text_decimal_from_text(v_srcroot, v_omitted_decimal_from_text);
            IF NOT v_omitted_decimal_from_text THEN
                v_out_obj.put('DecimalFromText', v_result_decimal_from_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('decimal_from_text') THEN
                    v_errors('decimal_from_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_from_number NUMBER;
            v_omitted_number_from_number BOOLEAN;
        BEGIN
            v_result_number_from_number := fn_builtins_text_number_from_number(v_srcroot, v_omitted_number_from_number);
            IF NOT v_omitted_number_from_number THEN
                v_out_obj.put('NumberFromNumber', v_result_number_from_number);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_from_number') THEN
                    v_errors('number_from_number') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_from_expr NUMBER;
            v_omitted_number_from_expr BOOLEAN;
        BEGIN
            v_result_number_from_expr := fn_builtins_text_number_from_expr(v_srcroot, v_omitted_number_from_expr);
            IF NOT v_omitted_number_from_expr THEN
                v_out_obj.put('NumberFromExpr', v_result_number_from_expr);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_from_expr') THEN
                    v_errors('number_from_expr') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_number VARCHAR2(4000 CHAR);
            v_omitted_text_from_number BOOLEAN;
        BEGIN
            v_result_text_from_number := fn_builtins_text_text_from_number(v_srcroot, v_omitted_text_from_number);
            IF NOT v_omitted_text_from_number THEN
                v_out_obj.put('TextFromNumber', v_result_text_from_number);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_number') THEN
                    v_errors('text_from_number') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_whole VARCHAR2(4000 CHAR);
            v_omitted_text_from_whole BOOLEAN;
        BEGIN
            v_result_text_from_whole := fn_builtins_text_text_from_whole(v_srcroot, v_omitted_text_from_whole);
            IF NOT v_omitted_text_from_whole THEN
                v_out_obj.put('TextFromWhole', v_result_text_from_whole);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_whole') THEN
                    v_errors('text_from_whole') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_small VARCHAR2(4000 CHAR);
            v_omitted_text_from_small BOOLEAN;
        BEGIN
            v_result_text_from_small := fn_builtins_text_text_from_small(v_srcroot, v_omitted_text_from_small);
            IF NOT v_omitted_text_from_small THEN
                v_out_obj.put('TextFromSmall', v_result_text_from_small);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_small') THEN
                    v_errors('text_from_small') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_text VARCHAR2(4000 CHAR);
            v_omitted_text_from_text BOOLEAN;
        BEGIN
            v_result_text_from_text := fn_builtins_text_text_from_text(v_srcroot, v_omitted_text_from_text);
            IF NOT v_omitted_text_from_text THEN
                v_out_obj.put('TextFromText', v_result_text_from_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_text') THEN
                    v_errors('text_from_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_bool VARCHAR2(4000 CHAR);
            v_omitted_text_from_bool BOOLEAN;
        BEGIN
            v_result_text_from_bool := fn_builtins_text_text_from_bool(v_srcroot, v_omitted_text_from_bool);
            IF NOT v_omitted_text_from_bool THEN
                v_out_obj.put('TextFromBool', v_result_text_from_bool);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_bool') THEN
                    v_errors('text_from_bool') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_list VARCHAR2(4000 CHAR);
            v_omitted_text_from_list BOOLEAN;
        BEGIN
            v_result_text_from_list := fn_builtins_text_text_from_list(v_srcroot, v_omitted_text_from_list);
            IF NOT v_omitted_text_from_list THEN
                v_out_obj.put('TextFromList', v_result_text_from_list);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_list') THEN
                    v_errors('text_from_list') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_expr VARCHAR2(4000 CHAR);
            v_omitted_text_from_expr BOOLEAN;
        BEGIN
            v_result_text_from_expr := fn_builtins_text_text_from_expr(v_srcroot, v_omitted_text_from_expr);
            IF NOT v_omitted_text_from_expr THEN
                v_out_obj.put('TextFromExpr', v_result_text_from_expr);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_expr') THEN
                    v_errors('text_from_expr') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_concat VARCHAR2(4000 CHAR);
            v_omitted_text_from_concat BOOLEAN;
        BEGIN
            v_result_text_from_concat := fn_builtins_text_text_from_concat(v_srcroot, v_omitted_text_from_concat);
            IF NOT v_omitted_text_from_concat THEN
                v_out_obj.put('TextFromConcat', v_result_text_from_concat);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_concat') THEN
                    v_errors('text_from_concat') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc VARCHAR2(4000 CHAR);
            v_omitted_utc BOOLEAN;
        BEGIN
            v_result_utc := fn_builtins_text_utc(v_srcroot, v_omitted_utc);
            IF NOT v_omitted_utc THEN
                v_out_obj.put('Utc', v_result_utc);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc') THEN
                    v_errors('utc') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc_fraction VARCHAR2(4000 CHAR);
            v_omitted_utc_fraction BOOLEAN;
        BEGIN
            v_result_utc_fraction := fn_builtins_text_utc_fraction(v_srcroot, v_omitted_utc_fraction);
            IF NOT v_omitted_utc_fraction THEN
                v_out_obj.put('UtcFraction', v_result_utc_fraction);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc_fraction') THEN
                    v_errors('utc_fraction') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc_from_z VARCHAR2(4000 CHAR);
            v_omitted_utc_from_z BOOLEAN;
        BEGIN
            v_result_utc_from_z := fn_builtins_text_utc_from_z(v_srcroot, v_omitted_utc_from_z);
            IF NOT v_omitted_utc_from_z THEN
                v_out_obj.put('UtcFromZ', v_result_utc_from_z);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc_from_z') THEN
                    v_errors('utc_from_z') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc_naive VARCHAR2(4000 CHAR);
            v_omitted_utc_naive BOOLEAN;
        BEGIN
            v_result_utc_naive := fn_builtins_text_utc_naive(v_srcroot, v_omitted_utc_naive);
            IF NOT v_omitted_utc_naive THEN
                v_out_obj.put('UtcNaive', v_result_utc_naive);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc_naive') THEN
                    v_errors('utc_naive') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rfc VARCHAR2(4000 CHAR);
            v_omitted_rfc BOOLEAN;
        BEGIN
            v_result_rfc := fn_builtins_text_rfc(v_srcroot, v_omitted_rfc);
            IF NOT v_omitted_rfc THEN
                v_out_obj.put('Rfc', v_result_rfc);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rfc') THEN
                    v_errors('rfc') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rfc_naive VARCHAR2(4000 CHAR);
            v_omitted_rfc_naive BOOLEAN;
        BEGIN
            v_result_rfc_naive := fn_builtins_text_rfc_naive(v_srcroot, v_omitted_rfc_naive);
            IF NOT v_omitted_rfc_naive THEN
                v_out_obj.put('RfcNaive', v_result_rfc_naive);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rfc_naive') THEN
                    v_errors('rfc_naive') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rfc_zero VARCHAR2(4000 CHAR);
            v_omitted_rfc_zero BOOLEAN;
        BEGIN
            v_result_rfc_zero := fn_builtins_text_rfc_zero(v_srcroot, v_omitted_rfc_zero);
            IF NOT v_omitted_rfc_zero THEN
                v_out_obj.put('RfcZero', v_result_rfc_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rfc_zero') THEN
                    v_errors('rfc_zero') := SQLERRM;
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
                v_payload.put('mapping', 'builtins_text');
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
                v_payload.put('mapping', 'builtins_text');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_builtins_text;

    PROCEDURE map_builtins_text_safe (
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
            v_result_replaced VARCHAR2(4000 CHAR);
            v_omitted_replaced BOOLEAN;
        BEGIN
            v_result_replaced := fn_builtins_text_replaced(v_srcroot, v_omitted_replaced);
            IF NOT v_omitted_replaced THEN
                v_out_obj.put('Replaced', v_result_replaced);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('replaced') THEN
                    v_errors('replaced') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_removed VARCHAR2(4000 CHAR);
            v_omitted_removed BOOLEAN;
        BEGIN
            v_result_removed := fn_builtins_text_removed(v_srcroot, v_omitted_removed);
            IF NOT v_omitted_removed THEN
                v_out_obj.put('Removed', v_result_removed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('removed') THEN
                    v_errors('removed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_prefix VARCHAR2(4000 CHAR);
            v_omitted_prefix BOOLEAN;
        BEGIN
            v_result_prefix := fn_builtins_text_prefix(v_srcroot, v_omitted_prefix);
            IF NOT v_omitted_prefix THEN
                v_out_obj.put('Prefix', v_result_prefix);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('prefix') THEN
                    v_errors('prefix') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_prefix_absent VARCHAR2(4000 CHAR);
            v_omitted_prefix_absent BOOLEAN;
        BEGIN
            v_result_prefix_absent := fn_builtins_text_prefix_absent(v_srcroot, v_omitted_prefix_absent);
            IF NOT v_omitted_prefix_absent THEN
                v_out_obj.put('PrefixAbsent', v_result_prefix_absent);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('prefix_absent') THEN
                    v_errors('prefix_absent') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_digits VARCHAR2(4000 CHAR);
            v_omitted_digits BOOLEAN;
        BEGIN
            v_result_digits := fn_builtins_text_digits(v_srcroot, v_omitted_digits);
            IF NOT v_omitted_digits THEN
                v_out_obj.put('Digits', v_result_digits);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('digits') THEN
                    v_errors('digits') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_swapped VARCHAR2(4000 CHAR);
            v_omitted_swapped BOOLEAN;
        BEGIN
            v_result_swapped := fn_builtins_text_swapped(v_srcroot, v_omitted_swapped);
            IF NOT v_omitted_swapped THEN
                v_out_obj.put('Swapped', v_result_swapped);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('swapped') THEN
                    v_errors('swapped') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_group VARCHAR2(4000 CHAR);
            v_omitted_group BOOLEAN;
        BEGIN
            v_result_group := fn_builtins_text_group(v_srcroot, v_omitted_group);
            IF NOT v_omitted_group THEN
                v_out_obj.put('Group', v_result_group);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('group') THEN
                    v_errors('group') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_whole VARCHAR2(4000 CHAR);
            v_omitted_whole BOOLEAN;
        BEGIN
            v_result_whole := fn_builtins_text_whole(v_srcroot, v_omitted_whole);
            IF NOT v_omitted_whole THEN
                v_out_obj.put('Whole', v_result_whole);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('whole') THEN
                    v_errors('whole') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_no_group VARCHAR2(4000 CHAR);
            v_omitted_no_group BOOLEAN;
        BEGIN
            v_result_no_group := fn_builtins_text_no_group(v_srcroot, v_omitted_no_group);
            IF NOT v_omitted_no_group THEN
                v_out_obj.put('NoGroup', v_result_no_group);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('no_group') THEN
                    v_errors('no_group') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed VARCHAR2(4000 CHAR);
            v_omitted_fixed BOOLEAN;
        BEGIN
            v_result_fixed := fn_builtins_text_fixed(v_srcroot, v_omitted_fixed);
            IF NOT v_omitted_fixed THEN
                v_out_obj.put('Fixed', v_result_fixed);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed') THEN
                    v_errors('fixed') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed_rounded VARCHAR2(4000 CHAR);
            v_omitted_fixed_rounded BOOLEAN;
        BEGIN
            v_result_fixed_rounded := fn_builtins_text_fixed_rounded(v_srcroot, v_omitted_fixed_rounded);
            IF NOT v_omitted_fixed_rounded THEN
                v_out_obj.put('FixedRounded', v_result_fixed_rounded);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed_rounded') THEN
                    v_errors('fixed_rounded') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed_whole VARCHAR2(4000 CHAR);
            v_omitted_fixed_whole BOOLEAN;
        BEGIN
            v_result_fixed_whole := fn_builtins_text_fixed_whole(v_srcroot, v_omitted_fixed_whole);
            IF NOT v_omitted_fixed_whole THEN
                v_out_obj.put('FixedWhole', v_result_fixed_whole);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed_whole') THEN
                    v_errors('fixed_whole') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_fixed_negative VARCHAR2(4000 CHAR);
            v_omitted_fixed_negative BOOLEAN;
        BEGIN
            v_result_fixed_negative := fn_builtins_text_fixed_negative(v_srcroot, v_omitted_fixed_negative);
            IF NOT v_omitted_fixed_negative THEN
                v_out_obj.put('FixedNegative', v_result_fixed_negative);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('fixed_negative') THEN
                    v_errors('fixed_negative') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rounded NUMBER;
            v_omitted_rounded BOOLEAN;
        BEGIN
            v_result_rounded := fn_builtins_text_rounded(v_srcroot, v_omitted_rounded);
            IF NOT v_omitted_rounded THEN
                v_out_obj.put('Rounded', v_result_rounded);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rounded') THEN
                    v_errors('rounded') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_from_text NUMBER;
            v_omitted_number_from_text BOOLEAN;
        BEGIN
            v_result_number_from_text := fn_builtins_text_number_from_text(v_srcroot, v_omitted_number_from_text);
            IF NOT v_omitted_number_from_text THEN
                v_out_obj.put('NumberFromText', v_result_number_from_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_from_text') THEN
                    v_errors('number_from_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_decimal_from_text NUMBER;
            v_omitted_decimal_from_text BOOLEAN;
        BEGIN
            v_result_decimal_from_text := fn_builtins_text_decimal_from_text(v_srcroot, v_omitted_decimal_from_text);
            IF NOT v_omitted_decimal_from_text THEN
                v_out_obj.put('DecimalFromText', v_result_decimal_from_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('decimal_from_text') THEN
                    v_errors('decimal_from_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_from_number NUMBER;
            v_omitted_number_from_number BOOLEAN;
        BEGIN
            v_result_number_from_number := fn_builtins_text_number_from_number(v_srcroot, v_omitted_number_from_number);
            IF NOT v_omitted_number_from_number THEN
                v_out_obj.put('NumberFromNumber', v_result_number_from_number);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_from_number') THEN
                    v_errors('number_from_number') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_from_expr NUMBER;
            v_omitted_number_from_expr BOOLEAN;
        BEGIN
            v_result_number_from_expr := fn_builtins_text_number_from_expr(v_srcroot, v_omitted_number_from_expr);
            IF NOT v_omitted_number_from_expr THEN
                v_out_obj.put('NumberFromExpr', v_result_number_from_expr);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_from_expr') THEN
                    v_errors('number_from_expr') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_number VARCHAR2(4000 CHAR);
            v_omitted_text_from_number BOOLEAN;
        BEGIN
            v_result_text_from_number := fn_builtins_text_text_from_number(v_srcroot, v_omitted_text_from_number);
            IF NOT v_omitted_text_from_number THEN
                v_out_obj.put('TextFromNumber', v_result_text_from_number);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_number') THEN
                    v_errors('text_from_number') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_whole VARCHAR2(4000 CHAR);
            v_omitted_text_from_whole BOOLEAN;
        BEGIN
            v_result_text_from_whole := fn_builtins_text_text_from_whole(v_srcroot, v_omitted_text_from_whole);
            IF NOT v_omitted_text_from_whole THEN
                v_out_obj.put('TextFromWhole', v_result_text_from_whole);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_whole') THEN
                    v_errors('text_from_whole') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_small VARCHAR2(4000 CHAR);
            v_omitted_text_from_small BOOLEAN;
        BEGIN
            v_result_text_from_small := fn_builtins_text_text_from_small(v_srcroot, v_omitted_text_from_small);
            IF NOT v_omitted_text_from_small THEN
                v_out_obj.put('TextFromSmall', v_result_text_from_small);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_small') THEN
                    v_errors('text_from_small') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_text VARCHAR2(4000 CHAR);
            v_omitted_text_from_text BOOLEAN;
        BEGIN
            v_result_text_from_text := fn_builtins_text_text_from_text(v_srcroot, v_omitted_text_from_text);
            IF NOT v_omitted_text_from_text THEN
                v_out_obj.put('TextFromText', v_result_text_from_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_text') THEN
                    v_errors('text_from_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_bool VARCHAR2(4000 CHAR);
            v_omitted_text_from_bool BOOLEAN;
        BEGIN
            v_result_text_from_bool := fn_builtins_text_text_from_bool(v_srcroot, v_omitted_text_from_bool);
            IF NOT v_omitted_text_from_bool THEN
                v_out_obj.put('TextFromBool', v_result_text_from_bool);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_bool') THEN
                    v_errors('text_from_bool') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_list VARCHAR2(4000 CHAR);
            v_omitted_text_from_list BOOLEAN;
        BEGIN
            v_result_text_from_list := fn_builtins_text_text_from_list(v_srcroot, v_omitted_text_from_list);
            IF NOT v_omitted_text_from_list THEN
                v_out_obj.put('TextFromList', v_result_text_from_list);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_list') THEN
                    v_errors('text_from_list') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_expr VARCHAR2(4000 CHAR);
            v_omitted_text_from_expr BOOLEAN;
        BEGIN
            v_result_text_from_expr := fn_builtins_text_text_from_expr(v_srcroot, v_omitted_text_from_expr);
            IF NOT v_omitted_text_from_expr THEN
                v_out_obj.put('TextFromExpr', v_result_text_from_expr);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_expr') THEN
                    v_errors('text_from_expr') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text_from_concat VARCHAR2(4000 CHAR);
            v_omitted_text_from_concat BOOLEAN;
        BEGIN
            v_result_text_from_concat := fn_builtins_text_text_from_concat(v_srcroot, v_omitted_text_from_concat);
            IF NOT v_omitted_text_from_concat THEN
                v_out_obj.put('TextFromConcat', v_result_text_from_concat);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text_from_concat') THEN
                    v_errors('text_from_concat') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc VARCHAR2(4000 CHAR);
            v_omitted_utc BOOLEAN;
        BEGIN
            v_result_utc := fn_builtins_text_utc(v_srcroot, v_omitted_utc);
            IF NOT v_omitted_utc THEN
                v_out_obj.put('Utc', v_result_utc);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc') THEN
                    v_errors('utc') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc_fraction VARCHAR2(4000 CHAR);
            v_omitted_utc_fraction BOOLEAN;
        BEGIN
            v_result_utc_fraction := fn_builtins_text_utc_fraction(v_srcroot, v_omitted_utc_fraction);
            IF NOT v_omitted_utc_fraction THEN
                v_out_obj.put('UtcFraction', v_result_utc_fraction);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc_fraction') THEN
                    v_errors('utc_fraction') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc_from_z VARCHAR2(4000 CHAR);
            v_omitted_utc_from_z BOOLEAN;
        BEGIN
            v_result_utc_from_z := fn_builtins_text_utc_from_z(v_srcroot, v_omitted_utc_from_z);
            IF NOT v_omitted_utc_from_z THEN
                v_out_obj.put('UtcFromZ', v_result_utc_from_z);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc_from_z') THEN
                    v_errors('utc_from_z') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_utc_naive VARCHAR2(4000 CHAR);
            v_omitted_utc_naive BOOLEAN;
        BEGIN
            v_result_utc_naive := fn_builtins_text_utc_naive(v_srcroot, v_omitted_utc_naive);
            IF NOT v_omitted_utc_naive THEN
                v_out_obj.put('UtcNaive', v_result_utc_naive);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('utc_naive') THEN
                    v_errors('utc_naive') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rfc VARCHAR2(4000 CHAR);
            v_omitted_rfc BOOLEAN;
        BEGIN
            v_result_rfc := fn_builtins_text_rfc(v_srcroot, v_omitted_rfc);
            IF NOT v_omitted_rfc THEN
                v_out_obj.put('Rfc', v_result_rfc);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rfc') THEN
                    v_errors('rfc') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rfc_naive VARCHAR2(4000 CHAR);
            v_omitted_rfc_naive BOOLEAN;
        BEGIN
            v_result_rfc_naive := fn_builtins_text_rfc_naive(v_srcroot, v_omitted_rfc_naive);
            IF NOT v_omitted_rfc_naive THEN
                v_out_obj.put('RfcNaive', v_result_rfc_naive);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rfc_naive') THEN
                    v_errors('rfc_naive') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_rfc_zero VARCHAR2(4000 CHAR);
            v_omitted_rfc_zero BOOLEAN;
        BEGIN
            v_result_rfc_zero := fn_builtins_text_rfc_zero(v_srcroot, v_omitted_rfc_zero);
            IF NOT v_omitted_rfc_zero THEN
                v_out_obj.put('RfcZero', v_result_rfc_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rfc_zero') THEN
                    v_errors('rfc_zero') := SQLERRM;
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
    END map_builtins_text_safe;
END J2JME_MAP_BUILTINS_TEXT;
/
