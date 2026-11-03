CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_TRUTHINESS AS
    PROCEDURE map_truthiness (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_truthiness_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_TRUTHINESS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_TRUTHINESS AS
    FUNCTION fn_truthiness_missing(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_missing__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_missing__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('missing')) THEN 'T' ELSE 'F' END);
        IF v_missing__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_missing__ret;
    END fn_truthiness_missing;

    FUNCTION fn_truthiness_json_null(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_json_null__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_json_null__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('json_null')) THEN 'T' ELSE 'F' END);
        IF v_json_null__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_json_null__ret;
    END fn_truthiness_json_null;

    FUNCTION fn_truthiness_bool_false(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_bool_false__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_bool_false__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('bool_false')) THEN 'T' ELSE 'F' END);
        IF v_bool_false__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_bool_false__ret;
    END fn_truthiness_bool_false;

    FUNCTION fn_truthiness_zero(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_zero__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_zero__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('zero')) THEN 'T' ELSE 'F' END);
        IF v_zero__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_zero__ret;
    END fn_truthiness_zero;

    FUNCTION fn_truthiness_zero_float(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_zero_float__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_zero_float__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('zero_float')) THEN 'T' ELSE 'F' END);
        IF v_zero_float__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_zero_float__ret;
    END fn_truthiness_zero_float;

    FUNCTION fn_truthiness_empty_string(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_empty_string__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_empty_string__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('empty_string')) THEN 'T' ELSE 'F' END);
        IF v_empty_string__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_empty_string__ret;
    END fn_truthiness_empty_string;

    FUNCTION fn_truthiness_empty_array(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_empty_array__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_empty_array__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('empty_array')) THEN 'T' ELSE 'F' END);
        IF v_empty_array__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_empty_array__ret;
    END fn_truthiness_empty_array;

    FUNCTION fn_truthiness_empty_object(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_empty_object__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_empty_object__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('empty_object')) THEN 'T' ELSE 'F' END);
        IF v_empty_object__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_empty_object__ret;
    END fn_truthiness_empty_object;

    FUNCTION fn_truthiness_bool_true(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_bool_true__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_bool_true__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('bool_true')) THEN 'T' ELSE 'F' END);
        IF v_bool_true__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_bool_true__ret;
    END fn_truthiness_bool_true;

    FUNCTION fn_truthiness_one(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_one__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_one__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('one')) THEN 'T' ELSE 'F' END);
        IF v_one__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_one__ret;
    END fn_truthiness_one;

    FUNCTION fn_truthiness_text(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_text__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_text__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('text')) THEN 'T' ELSE 'F' END);
        IF v_text__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_text__ret;
    END fn_truthiness_text;

    FUNCTION fn_truthiness_zero_string(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_zero_string__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_zero_string__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('zero_string')) THEN 'T' ELSE 'F' END);
        IF v_zero_string__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_zero_string__ret;
    END fn_truthiness_zero_string;

    FUNCTION fn_truthiness_array(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_array__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_array__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('array')) THEN 'T' ELSE 'F' END);
        IF v_array__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_array__ret;
    END fn_truthiness_array;

    FUNCTION fn_truthiness_object(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_object__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_object__ret := (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('object')) THEN 'T' ELSE 'F' END);
        IF v_object__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_object__ret;
    END fn_truthiness_object;

    PROCEDURE map_truthiness (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_missing VARCHAR2(4000 CHAR);
            v_omitted_missing BOOLEAN;
        BEGIN
            v_result_missing := fn_truthiness_missing(v_srcroot, v_omitted_missing);
            IF NOT v_omitted_missing THEN
                v_out_obj.put('Missing', v_result_missing);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('missing') THEN
                    v_errors('missing') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_json_null VARCHAR2(4000 CHAR);
            v_omitted_json_null BOOLEAN;
        BEGIN
            v_result_json_null := fn_truthiness_json_null(v_srcroot, v_omitted_json_null);
            IF NOT v_omitted_json_null THEN
                v_out_obj.put('JsonNull', v_result_json_null);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('json_null') THEN
                    v_errors('json_null') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_bool_false VARCHAR2(4000 CHAR);
            v_omitted_bool_false BOOLEAN;
        BEGIN
            v_result_bool_false := fn_truthiness_bool_false(v_srcroot, v_omitted_bool_false);
            IF NOT v_omitted_bool_false THEN
                v_out_obj.put('BoolFalse', v_result_bool_false);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('bool_false') THEN
                    v_errors('bool_false') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_zero VARCHAR2(4000 CHAR);
            v_omitted_zero BOOLEAN;
        BEGIN
            v_result_zero := fn_truthiness_zero(v_srcroot, v_omitted_zero);
            IF NOT v_omitted_zero THEN
                v_out_obj.put('Zero', v_result_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('zero') THEN
                    v_errors('zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_zero_float VARCHAR2(4000 CHAR);
            v_omitted_zero_float BOOLEAN;
        BEGIN
            v_result_zero_float := fn_truthiness_zero_float(v_srcroot, v_omitted_zero_float);
            IF NOT v_omitted_zero_float THEN
                v_out_obj.put('ZeroFloat', v_result_zero_float);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('zero_float') THEN
                    v_errors('zero_float') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_string VARCHAR2(4000 CHAR);
            v_omitted_empty_string BOOLEAN;
        BEGIN
            v_result_empty_string := fn_truthiness_empty_string(v_srcroot, v_omitted_empty_string);
            IF NOT v_omitted_empty_string THEN
                v_out_obj.put('EmptyString', v_result_empty_string);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_string') THEN
                    v_errors('empty_string') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_array VARCHAR2(4000 CHAR);
            v_omitted_empty_array BOOLEAN;
        BEGIN
            v_result_empty_array := fn_truthiness_empty_array(v_srcroot, v_omitted_empty_array);
            IF NOT v_omitted_empty_array THEN
                v_out_obj.put('EmptyArray', v_result_empty_array);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_array') THEN
                    v_errors('empty_array') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_object VARCHAR2(4000 CHAR);
            v_omitted_empty_object BOOLEAN;
        BEGIN
            v_result_empty_object := fn_truthiness_empty_object(v_srcroot, v_omitted_empty_object);
            IF NOT v_omitted_empty_object THEN
                v_out_obj.put('EmptyObject', v_result_empty_object);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_object') THEN
                    v_errors('empty_object') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_bool_true VARCHAR2(4000 CHAR);
            v_omitted_bool_true BOOLEAN;
        BEGIN
            v_result_bool_true := fn_truthiness_bool_true(v_srcroot, v_omitted_bool_true);
            IF NOT v_omitted_bool_true THEN
                v_out_obj.put('BoolTrue', v_result_bool_true);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('bool_true') THEN
                    v_errors('bool_true') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_one VARCHAR2(4000 CHAR);
            v_omitted_one BOOLEAN;
        BEGIN
            v_result_one := fn_truthiness_one(v_srcroot, v_omitted_one);
            IF NOT v_omitted_one THEN
                v_out_obj.put('One', v_result_one);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('one') THEN
                    v_errors('one') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text VARCHAR2(4000 CHAR);
            v_omitted_text BOOLEAN;
        BEGIN
            v_result_text := fn_truthiness_text(v_srcroot, v_omitted_text);
            IF NOT v_omitted_text THEN
                v_out_obj.put('Text', v_result_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text') THEN
                    v_errors('text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_zero_string VARCHAR2(4000 CHAR);
            v_omitted_zero_string BOOLEAN;
        BEGIN
            v_result_zero_string := fn_truthiness_zero_string(v_srcroot, v_omitted_zero_string);
            IF NOT v_omitted_zero_string THEN
                v_out_obj.put('ZeroString', v_result_zero_string);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('zero_string') THEN
                    v_errors('zero_string') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_array VARCHAR2(4000 CHAR);
            v_omitted_array BOOLEAN;
        BEGIN
            v_result_array := fn_truthiness_array(v_srcroot, v_omitted_array);
            IF NOT v_omitted_array THEN
                v_out_obj.put('Array', v_result_array);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('array') THEN
                    v_errors('array') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_object VARCHAR2(4000 CHAR);
            v_omitted_object BOOLEAN;
        BEGIN
            v_result_object := fn_truthiness_object(v_srcroot, v_omitted_object);
            IF NOT v_omitted_object THEN
                v_out_obj.put('Object', v_result_object);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('object') THEN
                    v_errors('object') := SQLERRM;
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
                v_payload.put('mapping', 'truthiness');
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
                v_payload.put('mapping', 'truthiness');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_truthiness;

    PROCEDURE map_truthiness_safe (
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
            v_result_missing VARCHAR2(4000 CHAR);
            v_omitted_missing BOOLEAN;
        BEGIN
            v_result_missing := fn_truthiness_missing(v_srcroot, v_omitted_missing);
            IF NOT v_omitted_missing THEN
                v_out_obj.put('Missing', v_result_missing);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('missing') THEN
                    v_errors('missing') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_json_null VARCHAR2(4000 CHAR);
            v_omitted_json_null BOOLEAN;
        BEGIN
            v_result_json_null := fn_truthiness_json_null(v_srcroot, v_omitted_json_null);
            IF NOT v_omitted_json_null THEN
                v_out_obj.put('JsonNull', v_result_json_null);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('json_null') THEN
                    v_errors('json_null') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_bool_false VARCHAR2(4000 CHAR);
            v_omitted_bool_false BOOLEAN;
        BEGIN
            v_result_bool_false := fn_truthiness_bool_false(v_srcroot, v_omitted_bool_false);
            IF NOT v_omitted_bool_false THEN
                v_out_obj.put('BoolFalse', v_result_bool_false);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('bool_false') THEN
                    v_errors('bool_false') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_zero VARCHAR2(4000 CHAR);
            v_omitted_zero BOOLEAN;
        BEGIN
            v_result_zero := fn_truthiness_zero(v_srcroot, v_omitted_zero);
            IF NOT v_omitted_zero THEN
                v_out_obj.put('Zero', v_result_zero);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('zero') THEN
                    v_errors('zero') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_zero_float VARCHAR2(4000 CHAR);
            v_omitted_zero_float BOOLEAN;
        BEGIN
            v_result_zero_float := fn_truthiness_zero_float(v_srcroot, v_omitted_zero_float);
            IF NOT v_omitted_zero_float THEN
                v_out_obj.put('ZeroFloat', v_result_zero_float);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('zero_float') THEN
                    v_errors('zero_float') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_string VARCHAR2(4000 CHAR);
            v_omitted_empty_string BOOLEAN;
        BEGIN
            v_result_empty_string := fn_truthiness_empty_string(v_srcroot, v_omitted_empty_string);
            IF NOT v_omitted_empty_string THEN
                v_out_obj.put('EmptyString', v_result_empty_string);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_string') THEN
                    v_errors('empty_string') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_array VARCHAR2(4000 CHAR);
            v_omitted_empty_array BOOLEAN;
        BEGIN
            v_result_empty_array := fn_truthiness_empty_array(v_srcroot, v_omitted_empty_array);
            IF NOT v_omitted_empty_array THEN
                v_out_obj.put('EmptyArray', v_result_empty_array);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_array') THEN
                    v_errors('empty_array') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_empty_object VARCHAR2(4000 CHAR);
            v_omitted_empty_object BOOLEAN;
        BEGIN
            v_result_empty_object := fn_truthiness_empty_object(v_srcroot, v_omitted_empty_object);
            IF NOT v_omitted_empty_object THEN
                v_out_obj.put('EmptyObject', v_result_empty_object);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('empty_object') THEN
                    v_errors('empty_object') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_bool_true VARCHAR2(4000 CHAR);
            v_omitted_bool_true BOOLEAN;
        BEGIN
            v_result_bool_true := fn_truthiness_bool_true(v_srcroot, v_omitted_bool_true);
            IF NOT v_omitted_bool_true THEN
                v_out_obj.put('BoolTrue', v_result_bool_true);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('bool_true') THEN
                    v_errors('bool_true') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_one VARCHAR2(4000 CHAR);
            v_omitted_one BOOLEAN;
        BEGIN
            v_result_one := fn_truthiness_one(v_srcroot, v_omitted_one);
            IF NOT v_omitted_one THEN
                v_out_obj.put('One', v_result_one);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('one') THEN
                    v_errors('one') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_text VARCHAR2(4000 CHAR);
            v_omitted_text BOOLEAN;
        BEGIN
            v_result_text := fn_truthiness_text(v_srcroot, v_omitted_text);
            IF NOT v_omitted_text THEN
                v_out_obj.put('Text', v_result_text);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('text') THEN
                    v_errors('text') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_zero_string VARCHAR2(4000 CHAR);
            v_omitted_zero_string BOOLEAN;
        BEGIN
            v_result_zero_string := fn_truthiness_zero_string(v_srcroot, v_omitted_zero_string);
            IF NOT v_omitted_zero_string THEN
                v_out_obj.put('ZeroString', v_result_zero_string);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('zero_string') THEN
                    v_errors('zero_string') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_array VARCHAR2(4000 CHAR);
            v_omitted_array BOOLEAN;
        BEGIN
            v_result_array := fn_truthiness_array(v_srcroot, v_omitted_array);
            IF NOT v_omitted_array THEN
                v_out_obj.put('Array', v_result_array);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('array') THEN
                    v_errors('array') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_object VARCHAR2(4000 CHAR);
            v_omitted_object BOOLEAN;
        BEGIN
            v_result_object := fn_truthiness_object(v_srcroot, v_omitted_object);
            IF NOT v_omitted_object THEN
                v_out_obj.put('Object', v_result_object);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('object') THEN
                    v_errors('object') := SQLERRM;
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
    END map_truthiness_safe;
END J2JME_MAP_TRUTHINESS;
/
