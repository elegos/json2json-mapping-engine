CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_EMPTY_TEXT AS
    PROCEDURE map_empty_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_empty_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_EMPTY_TEXT;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_EMPTY_TEXT AS
    FUNCTION fn_empty_text_nth_0(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 0), '~');
    END fn_empty_text_nth_0;

    FUNCTION fn_empty_text_nth_1(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 1);
    END fn_empty_text_nth_1;

    FUNCTION fn_empty_text_nth_2(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 2);
    END fn_empty_text_nth_2;

    FUNCTION fn_empty_text_nth_3(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 3), '~');
    END fn_empty_text_nth_3;

    FUNCTION fn_empty_text_nth_5(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 5), '~');
    END fn_empty_text_nth_5;

    FUNCTION fn_empty_text_nth_6(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 6);
    END fn_empty_text_nth_6;

    FUNCTION fn_empty_text_nth_7(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 7), '~');
    END fn_empty_text_nth_7;

    FUNCTION fn_empty_text_nth_8(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 8), '~');
    END fn_empty_text_nth_8;

    FUNCTION fn_empty_text_first(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN MAPPING_OWNER.J2JME_FUNCTIONS.split_first(p_root.get_String('s'), '|');
    END fn_empty_text_first;

    FUNCTION fn_empty_text_first_leading_empty(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.split_first(p_root.get_String('s2'), '|'), '~');
    END fn_empty_text_first_leading_empty;

    FUNCTION fn_empty_text_first_of_blank(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.split_first(p_root.get_String('blank'), '|'), '~');
    END fn_empty_text_first_of_blank;

    FUNCTION fn_empty_text_blank(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(p_root.get_String('blank'), '~');
    END fn_empty_text_blank;

    FUNCTION fn_empty_text_concat_blanks(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE((p_root.get_String('blank') || p_root.get_String('blank')), '~');
    END fn_empty_text_concat_blanks;

    FUNCTION fn_empty_text_replace_to_empty(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN COALESCE(REPLACE(p_root.get_String('word'), 'x', ''), '~');
    END fn_empty_text_replace_to_empty;

    FUNCTION fn_empty_text_is_empty_blank(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('blank'), FALSE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_blank;

    FUNCTION fn_empty_text_is_empty_missing(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('missing'), FALSE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_missing;

    FUNCTION fn_empty_text_is_empty_null(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('json_null'), FALSE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_null;

    FUNCTION fn_empty_text_is_empty_text(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('word'), FALSE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_text;

    FUNCTION fn_empty_text_is_empty_zero(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('zero'), FALSE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_zero;

    FUNCTION fn_empty_text_is_empty_zero_option(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('zero'), TRUE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_zero_option;

    FUNCTION fn_empty_text_is_empty_number_option(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('num'), TRUE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_number_option;

    FUNCTION fn_empty_text_is_empty_false(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('flag'), TRUE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_false;

    FUNCTION fn_empty_text_is_empty_list(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE(MAPPING_OWNER.J2JME_FUNCTIONS.is_empty(p_root.get('list'), FALSE), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_list;

    FUNCTION fn_empty_text_is_empty_part(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE((MAPPING_OWNER.J2JME_FUNCTIONS.split_nth(p_root.get_String('s'), '|', 3) IS NULL), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_part;

    FUNCTION fn_empty_text_is_empty_rounded_zero(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN COALESCE((ROUND(p_root.get_Number('small')) IS NULL OR (TRUE AND ROUND(p_root.get_Number('small')) = 0)), FALSE) THEN 'T' ELSE 'F' END);
    END fn_empty_text_is_empty_rounded_zero;

    PROCEDURE map_empty_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_nth_0 VARCHAR2(4000 CHAR);
            v_omitted_nth_0 BOOLEAN;
        BEGIN
            v_result_nth_0 := fn_empty_text_nth_0(v_srcroot, v_omitted_nth_0);
            IF NOT v_omitted_nth_0 THEN
                v_out_obj.put('Nth0', v_result_nth_0);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_0') THEN
                    v_errors('nth_0') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_1 VARCHAR2(4000 CHAR);
            v_omitted_nth_1 BOOLEAN;
        BEGIN
            v_result_nth_1 := fn_empty_text_nth_1(v_srcroot, v_omitted_nth_1);
            IF NOT v_omitted_nth_1 THEN
                v_out_obj.put('Nth1', v_result_nth_1);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_1') THEN
                    v_errors('nth_1') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_2 VARCHAR2(4000 CHAR);
            v_omitted_nth_2 BOOLEAN;
        BEGIN
            v_result_nth_2 := fn_empty_text_nth_2(v_srcroot, v_omitted_nth_2);
            IF NOT v_omitted_nth_2 THEN
                v_out_obj.put('Nth2', v_result_nth_2);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_2') THEN
                    v_errors('nth_2') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_3 VARCHAR2(4000 CHAR);
            v_omitted_nth_3 BOOLEAN;
        BEGIN
            v_result_nth_3 := fn_empty_text_nth_3(v_srcroot, v_omitted_nth_3);
            IF NOT v_omitted_nth_3 THEN
                v_out_obj.put('Nth3', v_result_nth_3);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_3') THEN
                    v_errors('nth_3') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_5 VARCHAR2(4000 CHAR);
            v_omitted_nth_5 BOOLEAN;
        BEGIN
            v_result_nth_5 := fn_empty_text_nth_5(v_srcroot, v_omitted_nth_5);
            IF NOT v_omitted_nth_5 THEN
                v_out_obj.put('Nth5', v_result_nth_5);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_5') THEN
                    v_errors('nth_5') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_6 VARCHAR2(4000 CHAR);
            v_omitted_nth_6 BOOLEAN;
        BEGIN
            v_result_nth_6 := fn_empty_text_nth_6(v_srcroot, v_omitted_nth_6);
            IF NOT v_omitted_nth_6 THEN
                v_out_obj.put('Nth6', v_result_nth_6);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_6') THEN
                    v_errors('nth_6') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_7 VARCHAR2(4000 CHAR);
            v_omitted_nth_7 BOOLEAN;
        BEGIN
            v_result_nth_7 := fn_empty_text_nth_7(v_srcroot, v_omitted_nth_7);
            IF NOT v_omitted_nth_7 THEN
                v_out_obj.put('Nth7', v_result_nth_7);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_7') THEN
                    v_errors('nth_7') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_8 VARCHAR2(4000 CHAR);
            v_omitted_nth_8 BOOLEAN;
        BEGIN
            v_result_nth_8 := fn_empty_text_nth_8(v_srcroot, v_omitted_nth_8);
            IF NOT v_omitted_nth_8 THEN
                v_out_obj.put('Nth8', v_result_nth_8);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_8') THEN
                    v_errors('nth_8') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first VARCHAR2(4000 CHAR);
            v_omitted_first BOOLEAN;
        BEGIN
            v_result_first := fn_empty_text_first(v_srcroot, v_omitted_first);
            IF NOT v_omitted_first THEN
                v_out_obj.put('First', v_result_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first') THEN
                    v_errors('first') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first_leading_empty VARCHAR2(4000 CHAR);
            v_omitted_first_leading_empty BOOLEAN;
        BEGIN
            v_result_first_leading_empty := fn_empty_text_first_leading_empty(v_srcroot, v_omitted_first_leading_empty);
            IF NOT v_omitted_first_leading_empty THEN
                v_out_obj.put('FirstLeadingEmpty', v_result_first_leading_empty);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first_leading_empty') THEN
                    v_errors('first_leading_empty') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first_of_blank VARCHAR2(4000 CHAR);
            v_omitted_first_of_blank BOOLEAN;
        BEGIN
            v_result_first_of_blank := fn_empty_text_first_of_blank(v_srcroot, v_omitted_first_of_blank);
            IF NOT v_omitted_first_of_blank THEN
                v_out_obj.put('FirstOfBlank', v_result_first_of_blank);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first_of_blank') THEN
                    v_errors('first_of_blank') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_blank VARCHAR2(4000 CHAR);
            v_omitted_blank BOOLEAN;
        BEGIN
            v_result_blank := fn_empty_text_blank(v_srcroot, v_omitted_blank);
            IF NOT v_omitted_blank THEN
                v_out_obj.put('Blank', v_result_blank);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('blank') THEN
                    v_errors('blank') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_concat_blanks VARCHAR2(4000 CHAR);
            v_omitted_concat_blanks BOOLEAN;
        BEGIN
            v_result_concat_blanks := fn_empty_text_concat_blanks(v_srcroot, v_omitted_concat_blanks);
            IF NOT v_omitted_concat_blanks THEN
                v_out_obj.put('ConcatBlanks', v_result_concat_blanks);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('concat_blanks') THEN
                    v_errors('concat_blanks') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_replace_to_empty VARCHAR2(4000 CHAR);
            v_omitted_replace_to_empty BOOLEAN;
        BEGIN
            v_result_replace_to_empty := fn_empty_text_replace_to_empty(v_srcroot, v_omitted_replace_to_empty);
            IF NOT v_omitted_replace_to_empty THEN
                v_out_obj.put('ReplaceToEmpty', v_result_replace_to_empty);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('replace_to_empty') THEN
                    v_errors('replace_to_empty') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_blank VARCHAR2(4000 CHAR);
            v_omitted_is_empty_blank BOOLEAN;
        BEGIN
            v_result_is_empty_blank := fn_empty_text_is_empty_blank(v_srcroot, v_omitted_is_empty_blank);
            IF NOT v_omitted_is_empty_blank THEN
                v_out_obj.put('IsEmptyBlank', v_result_is_empty_blank);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_blank') THEN
                    v_errors('is_empty_blank') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_missing VARCHAR2(4000 CHAR);
            v_omitted_is_empty_missing BOOLEAN;
        BEGIN
            v_result_is_empty_missing := fn_empty_text_is_empty_missing(v_srcroot, v_omitted_is_empty_missing);
            IF NOT v_omitted_is_empty_missing THEN
                v_out_obj.put('IsEmptyMissing', v_result_is_empty_missing);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_missing') THEN
                    v_errors('is_empty_missing') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_null VARCHAR2(4000 CHAR);
            v_omitted_is_empty_null BOOLEAN;
        BEGIN
            v_result_is_empty_null := fn_empty_text_is_empty_null(v_srcroot, v_omitted_is_empty_null);
            IF NOT v_omitted_is_empty_null THEN
                v_out_obj.put('IsEmptyNull', v_result_is_empty_null);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_null') THEN
                    v_errors('is_empty_null') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_text VARCHAR2(4000 CHAR);
            v_omitted_is_empty_text BOOLEAN;
        BEGIN
            v_result_is_empty_text := fn_empty_text_is_empty_text(v_srcroot, v_omitted_is_empty_text);
            IF NOT v_omitted_is_empty_text THEN
                v_out_obj.put('IsEmptyText', v_result_is_empty_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_text') THEN
                    v_errors('is_empty_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_zero VARCHAR2(4000 CHAR);
            v_omitted_is_empty_zero BOOLEAN;
        BEGIN
            v_result_is_empty_zero := fn_empty_text_is_empty_zero(v_srcroot, v_omitted_is_empty_zero);
            IF NOT v_omitted_is_empty_zero THEN
                v_out_obj.put('IsEmptyZero', v_result_is_empty_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_zero') THEN
                    v_errors('is_empty_zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_zero_option VARCHAR2(4000 CHAR);
            v_omitted_is_empty_zero_option BOOLEAN;
        BEGIN
            v_result_is_empty_zero_option := fn_empty_text_is_empty_zero_option(v_srcroot, v_omitted_is_empty_zero_option);
            IF NOT v_omitted_is_empty_zero_option THEN
                v_out_obj.put('IsEmptyZeroOption', v_result_is_empty_zero_option);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_zero_option') THEN
                    v_errors('is_empty_zero_option') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_number_option VARCHAR2(4000 CHAR);
            v_omitted_is_empty_number_option BOOLEAN;
        BEGIN
            v_result_is_empty_number_option := fn_empty_text_is_empty_number_option(v_srcroot, v_omitted_is_empty_number_option);
            IF NOT v_omitted_is_empty_number_option THEN
                v_out_obj.put('IsEmptyNumberOption', v_result_is_empty_number_option);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_number_option') THEN
                    v_errors('is_empty_number_option') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_false VARCHAR2(4000 CHAR);
            v_omitted_is_empty_false BOOLEAN;
        BEGIN
            v_result_is_empty_false := fn_empty_text_is_empty_false(v_srcroot, v_omitted_is_empty_false);
            IF NOT v_omitted_is_empty_false THEN
                v_out_obj.put('IsEmptyFalse', v_result_is_empty_false);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_false') THEN
                    v_errors('is_empty_false') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_list VARCHAR2(4000 CHAR);
            v_omitted_is_empty_list BOOLEAN;
        BEGIN
            v_result_is_empty_list := fn_empty_text_is_empty_list(v_srcroot, v_omitted_is_empty_list);
            IF NOT v_omitted_is_empty_list THEN
                v_out_obj.put('IsEmptyList', v_result_is_empty_list);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_list') THEN
                    v_errors('is_empty_list') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_part VARCHAR2(4000 CHAR);
            v_omitted_is_empty_part BOOLEAN;
        BEGIN
            v_result_is_empty_part := fn_empty_text_is_empty_part(v_srcroot, v_omitted_is_empty_part);
            IF NOT v_omitted_is_empty_part THEN
                v_out_obj.put('IsEmptyPart', v_result_is_empty_part);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_part') THEN
                    v_errors('is_empty_part') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_rounded_zero VARCHAR2(4000 CHAR);
            v_omitted_is_empty_rounded_zero BOOLEAN;
        BEGIN
            v_result_is_empty_rounded_zero := fn_empty_text_is_empty_rounded_zero(v_srcroot, v_omitted_is_empty_rounded_zero);
            IF NOT v_omitted_is_empty_rounded_zero THEN
                v_out_obj.put('IsEmptyRoundedZero', v_result_is_empty_rounded_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_rounded_zero') THEN
                    v_errors('is_empty_rounded_zero') := SQLERRM;
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
                v_payload.put('mapping', 'empty_text');
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
                v_payload.put('mapping', 'empty_text');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_empty_text;

    PROCEDURE map_empty_text_safe (
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
            v_result_nth_0 VARCHAR2(4000 CHAR);
            v_omitted_nth_0 BOOLEAN;
        BEGIN
            v_result_nth_0 := fn_empty_text_nth_0(v_srcroot, v_omitted_nth_0);
            IF NOT v_omitted_nth_0 THEN
                v_out_obj.put('Nth0', v_result_nth_0);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_0') THEN
                    v_errors('nth_0') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_1 VARCHAR2(4000 CHAR);
            v_omitted_nth_1 BOOLEAN;
        BEGIN
            v_result_nth_1 := fn_empty_text_nth_1(v_srcroot, v_omitted_nth_1);
            IF NOT v_omitted_nth_1 THEN
                v_out_obj.put('Nth1', v_result_nth_1);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_1') THEN
                    v_errors('nth_1') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_2 VARCHAR2(4000 CHAR);
            v_omitted_nth_2 BOOLEAN;
        BEGIN
            v_result_nth_2 := fn_empty_text_nth_2(v_srcroot, v_omitted_nth_2);
            IF NOT v_omitted_nth_2 THEN
                v_out_obj.put('Nth2', v_result_nth_2);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_2') THEN
                    v_errors('nth_2') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_3 VARCHAR2(4000 CHAR);
            v_omitted_nth_3 BOOLEAN;
        BEGIN
            v_result_nth_3 := fn_empty_text_nth_3(v_srcroot, v_omitted_nth_3);
            IF NOT v_omitted_nth_3 THEN
                v_out_obj.put('Nth3', v_result_nth_3);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_3') THEN
                    v_errors('nth_3') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_5 VARCHAR2(4000 CHAR);
            v_omitted_nth_5 BOOLEAN;
        BEGIN
            v_result_nth_5 := fn_empty_text_nth_5(v_srcroot, v_omitted_nth_5);
            IF NOT v_omitted_nth_5 THEN
                v_out_obj.put('Nth5', v_result_nth_5);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_5') THEN
                    v_errors('nth_5') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_6 VARCHAR2(4000 CHAR);
            v_omitted_nth_6 BOOLEAN;
        BEGIN
            v_result_nth_6 := fn_empty_text_nth_6(v_srcroot, v_omitted_nth_6);
            IF NOT v_omitted_nth_6 THEN
                v_out_obj.put('Nth6', v_result_nth_6);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_6') THEN
                    v_errors('nth_6') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_7 VARCHAR2(4000 CHAR);
            v_omitted_nth_7 BOOLEAN;
        BEGIN
            v_result_nth_7 := fn_empty_text_nth_7(v_srcroot, v_omitted_nth_7);
            IF NOT v_omitted_nth_7 THEN
                v_out_obj.put('Nth7', v_result_nth_7);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_7') THEN
                    v_errors('nth_7') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_nth_8 VARCHAR2(4000 CHAR);
            v_omitted_nth_8 BOOLEAN;
        BEGIN
            v_result_nth_8 := fn_empty_text_nth_8(v_srcroot, v_omitted_nth_8);
            IF NOT v_omitted_nth_8 THEN
                v_out_obj.put('Nth8', v_result_nth_8);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('nth_8') THEN
                    v_errors('nth_8') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first VARCHAR2(4000 CHAR);
            v_omitted_first BOOLEAN;
        BEGIN
            v_result_first := fn_empty_text_first(v_srcroot, v_omitted_first);
            IF NOT v_omitted_first THEN
                v_out_obj.put('First', v_result_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first') THEN
                    v_errors('first') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first_leading_empty VARCHAR2(4000 CHAR);
            v_omitted_first_leading_empty BOOLEAN;
        BEGIN
            v_result_first_leading_empty := fn_empty_text_first_leading_empty(v_srcroot, v_omitted_first_leading_empty);
            IF NOT v_omitted_first_leading_empty THEN
                v_out_obj.put('FirstLeadingEmpty', v_result_first_leading_empty);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first_leading_empty') THEN
                    v_errors('first_leading_empty') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_first_of_blank VARCHAR2(4000 CHAR);
            v_omitted_first_of_blank BOOLEAN;
        BEGIN
            v_result_first_of_blank := fn_empty_text_first_of_blank(v_srcroot, v_omitted_first_of_blank);
            IF NOT v_omitted_first_of_blank THEN
                v_out_obj.put('FirstOfBlank', v_result_first_of_blank);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first_of_blank') THEN
                    v_errors('first_of_blank') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_blank VARCHAR2(4000 CHAR);
            v_omitted_blank BOOLEAN;
        BEGIN
            v_result_blank := fn_empty_text_blank(v_srcroot, v_omitted_blank);
            IF NOT v_omitted_blank THEN
                v_out_obj.put('Blank', v_result_blank);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('blank') THEN
                    v_errors('blank') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_concat_blanks VARCHAR2(4000 CHAR);
            v_omitted_concat_blanks BOOLEAN;
        BEGIN
            v_result_concat_blanks := fn_empty_text_concat_blanks(v_srcroot, v_omitted_concat_blanks);
            IF NOT v_omitted_concat_blanks THEN
                v_out_obj.put('ConcatBlanks', v_result_concat_blanks);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('concat_blanks') THEN
                    v_errors('concat_blanks') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_replace_to_empty VARCHAR2(4000 CHAR);
            v_omitted_replace_to_empty BOOLEAN;
        BEGIN
            v_result_replace_to_empty := fn_empty_text_replace_to_empty(v_srcroot, v_omitted_replace_to_empty);
            IF NOT v_omitted_replace_to_empty THEN
                v_out_obj.put('ReplaceToEmpty', v_result_replace_to_empty);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('replace_to_empty') THEN
                    v_errors('replace_to_empty') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_blank VARCHAR2(4000 CHAR);
            v_omitted_is_empty_blank BOOLEAN;
        BEGIN
            v_result_is_empty_blank := fn_empty_text_is_empty_blank(v_srcroot, v_omitted_is_empty_blank);
            IF NOT v_omitted_is_empty_blank THEN
                v_out_obj.put('IsEmptyBlank', v_result_is_empty_blank);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_blank') THEN
                    v_errors('is_empty_blank') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_missing VARCHAR2(4000 CHAR);
            v_omitted_is_empty_missing BOOLEAN;
        BEGIN
            v_result_is_empty_missing := fn_empty_text_is_empty_missing(v_srcroot, v_omitted_is_empty_missing);
            IF NOT v_omitted_is_empty_missing THEN
                v_out_obj.put('IsEmptyMissing', v_result_is_empty_missing);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_missing') THEN
                    v_errors('is_empty_missing') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_null VARCHAR2(4000 CHAR);
            v_omitted_is_empty_null BOOLEAN;
        BEGIN
            v_result_is_empty_null := fn_empty_text_is_empty_null(v_srcroot, v_omitted_is_empty_null);
            IF NOT v_omitted_is_empty_null THEN
                v_out_obj.put('IsEmptyNull', v_result_is_empty_null);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_null') THEN
                    v_errors('is_empty_null') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_text VARCHAR2(4000 CHAR);
            v_omitted_is_empty_text BOOLEAN;
        BEGIN
            v_result_is_empty_text := fn_empty_text_is_empty_text(v_srcroot, v_omitted_is_empty_text);
            IF NOT v_omitted_is_empty_text THEN
                v_out_obj.put('IsEmptyText', v_result_is_empty_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_text') THEN
                    v_errors('is_empty_text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_zero VARCHAR2(4000 CHAR);
            v_omitted_is_empty_zero BOOLEAN;
        BEGIN
            v_result_is_empty_zero := fn_empty_text_is_empty_zero(v_srcroot, v_omitted_is_empty_zero);
            IF NOT v_omitted_is_empty_zero THEN
                v_out_obj.put('IsEmptyZero', v_result_is_empty_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_zero') THEN
                    v_errors('is_empty_zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_zero_option VARCHAR2(4000 CHAR);
            v_omitted_is_empty_zero_option BOOLEAN;
        BEGIN
            v_result_is_empty_zero_option := fn_empty_text_is_empty_zero_option(v_srcroot, v_omitted_is_empty_zero_option);
            IF NOT v_omitted_is_empty_zero_option THEN
                v_out_obj.put('IsEmptyZeroOption', v_result_is_empty_zero_option);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_zero_option') THEN
                    v_errors('is_empty_zero_option') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_number_option VARCHAR2(4000 CHAR);
            v_omitted_is_empty_number_option BOOLEAN;
        BEGIN
            v_result_is_empty_number_option := fn_empty_text_is_empty_number_option(v_srcroot, v_omitted_is_empty_number_option);
            IF NOT v_omitted_is_empty_number_option THEN
                v_out_obj.put('IsEmptyNumberOption', v_result_is_empty_number_option);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_number_option') THEN
                    v_errors('is_empty_number_option') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_false VARCHAR2(4000 CHAR);
            v_omitted_is_empty_false BOOLEAN;
        BEGIN
            v_result_is_empty_false := fn_empty_text_is_empty_false(v_srcroot, v_omitted_is_empty_false);
            IF NOT v_omitted_is_empty_false THEN
                v_out_obj.put('IsEmptyFalse', v_result_is_empty_false);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_false') THEN
                    v_errors('is_empty_false') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_list VARCHAR2(4000 CHAR);
            v_omitted_is_empty_list BOOLEAN;
        BEGIN
            v_result_is_empty_list := fn_empty_text_is_empty_list(v_srcroot, v_omitted_is_empty_list);
            IF NOT v_omitted_is_empty_list THEN
                v_out_obj.put('IsEmptyList', v_result_is_empty_list);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_list') THEN
                    v_errors('is_empty_list') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_part VARCHAR2(4000 CHAR);
            v_omitted_is_empty_part BOOLEAN;
        BEGIN
            v_result_is_empty_part := fn_empty_text_is_empty_part(v_srcroot, v_omitted_is_empty_part);
            IF NOT v_omitted_is_empty_part THEN
                v_out_obj.put('IsEmptyPart', v_result_is_empty_part);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_part') THEN
                    v_errors('is_empty_part') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_is_empty_rounded_zero VARCHAR2(4000 CHAR);
            v_omitted_is_empty_rounded_zero BOOLEAN;
        BEGIN
            v_result_is_empty_rounded_zero := fn_empty_text_is_empty_rounded_zero(v_srcroot, v_omitted_is_empty_rounded_zero);
            IF NOT v_omitted_is_empty_rounded_zero THEN
                v_out_obj.put('IsEmptyRoundedZero', v_result_is_empty_rounded_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('is_empty_rounded_zero') THEN
                    v_errors('is_empty_rounded_zero') := SQLERRM;
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
    END map_empty_text_safe;
END J2JME_MAP_EMPTY_TEXT;
/
