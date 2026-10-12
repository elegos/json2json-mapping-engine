CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_VALIDATION AS
    PROCEDURE map_validation (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_validation_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB,
        p_report OUT CLOB
    );
END J2JME_MAP_VALIDATION;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_VALIDATION AS
    FUNCTION fn_validation_check_vat(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN BOOLEAN IS
        v_check_vat__ret BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_check_vat__ret := ((NOT MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get('vatId'))) OR (COALESCE((CASE WHEN p_root.get_String('vatId') IS NULL THEN NULL WHEN REGEXP_LIKE(p_root.get_String('vatId'), '^[0-9]+$') THEN TRUE ELSE FALSE END), FALSE) AND (LENGTH(p_root.get_String('vatId')) = 11)));
        IF v_check_vat__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_check_vat__ret;
    END fn_validation_check_vat;

    FUNCTION fn_validation_check_amount(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN BOOLEAN IS
        v_check_amount__ret BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_check_amount__ret := (p_root.get_Number('amount') <= 10000);
        IF v_check_amount__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_check_amount__ret;
    END fn_validation_check_amount;

    FUNCTION fn_validation_check_positive(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN BOOLEAN IS
        v_check_positive__ret BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_check_positive__ret := (p_root.get_Number('amount') > 0);
        IF v_check_positive__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_check_positive__ret;
    END fn_validation_check_positive;

    FUNCTION fn_validation_the_id(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_the_id__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_the_id__ret := p_root.get_String('id');
        IF v_the_id__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_the_id__ret;
    END fn_validation_the_id;

    FUNCTION fn_validation_the_amount(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_the_amount__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_the_amount__ret := p_root.get_Number('amount');
        IF v_the_amount__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_the_amount__ret;
    END fn_validation_the_amount;

    FUNCTION fn_validation_the_vat(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_the_vat__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_the_vat__ret := p_root.get_String('vatId');
        IF v_the_vat__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_the_vat__ret;
    END fn_validation_the_vat;

    -- the input JSON Schema, sha256:3c1e48edcde751b5
    FUNCTION fn_validation_validation_schema_input RETURN CLOB IS
    BEGIN
        RETURN TO_CLOB('{"properties":{"amount":{"type":"number"},"currency":{"enum":["EUR","USD"],"type":"string"},"id":{"type":"string"},"vatId":{"type":"string"}},"required":["id","amount"],"type":"object"}');
    END fn_validation_validation_schema_input;

    -- the output JSON Schema, sha256:fb2e561c62cc47fd
    FUNCTION fn_validation_validation_schema_output RETURN CLOB IS
    BEGIN
        RETURN TO_CLOB('{"properties":{"amount":{"type":"number"},"id":{"type":"string"},"vat":{"type":"string"}},"required":["id","amount"],"type":"object"}');
    END fn_validation_validation_schema_output;

    PROCEDURE map_validation (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_report   JSON_ARRAY_T := JSON_ARRAY_T();
        v_rejected BOOLEAN := FALSE;
        v_schema_failed_input  BOOLEAN := FALSE;
        v_schema_failed_output BOOLEAN := FALSE;
        PROCEDURE add_failed(p_side IN VARCHAR2, p_code IN VARCHAR2, p_message IN VARCHAR2, p_action IN VARCHAR2) IS
            v_item JSON_OBJECT_T := JSON_OBJECT_T();
        BEGIN
            v_item.put('side', p_side);
            v_item.put('code', p_code);
            v_item.put('message', p_message);
            v_item.put('action', p_action);
            v_report.append(v_item);
            IF p_action = 'reject' THEN v_rejected := TRUE; END IF;
        END add_failed;
    BEGIN
        DECLARE
            v_doc    CLOB := p_src;
            v_schema CLOB := fn_validation_validation_schema_input;
            v_valid  NUMBER;
            v_paths  VARCHAR2(300);
            v_path   VARCHAR2(200);
            v_rep    VARCHAR2(4000);
            v_errs   JSON_ARRAY_T;
        BEGIN
            SELECT DBMS_JSON_SCHEMA.IS_VALID(JSON(v_doc), JSON(v_schema)) INTO v_valid FROM dual;
            IF v_valid = 0 THEN
                v_schema_failed_input := TRUE;
                BEGIN  -- where the document differs (the validator's own texts are not shipped)
                    SELECT JSON_QUERY(DBMS_JSON_SCHEMA.VALIDATE_REPORT(JSON(v_doc), JSON(v_schema)), '$.errors' RETURNING VARCHAR2(4000)) INTO v_rep FROM dual;
                    v_errs := JSON_ARRAY_T(v_rep);
                    FOR v_j IN 0 .. LEAST(v_errs.get_size, 6) - 1 LOOP
                        v_path := TREAT(v_errs.get(v_j) AS JSON_OBJECT_T).get_String('instancePath');
                        IF v_path <> '$' AND NVL(INSTR(v_paths, v_path), 0) = 0 AND NVL(LENGTH(v_paths), 0) < 200 THEN
                            v_paths := v_paths || CASE WHEN v_paths IS NULL THEN '' ELSE ', ' END || v_path;
                        END IF;
                    END LOOP;
                EXCEPTION WHEN OTHERS THEN NULL;
                END;
                add_failed('input', 'SCHEMA_INPUT', 'does not match the JSON Schema' || CASE WHEN v_paths IS NULL THEN '' ELSE ': ' || v_paths END, 'reject');
            END IF;
        END;
        DECLARE
            v_verdict BOOLEAN;
            v_omitted BOOLEAN;
        BEGIN
            v_verdict := fn_validation_check_vat(v_srcroot, v_omitted);
            IF NOT COALESCE(v_verdict, FALSE) THEN
                add_failed('input', 'VAT_FORMAT', 'vatId must be 11 digits', 'reject');
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_schema_failed_input THEN
                    add_failed('input', 'VAT_FORMAT', 'vatId must be 11 digits' || ' (the check could not be evaluated: ' || SQLERRM || ')', 'reject');
                END IF;
        END;
        DECLARE
            v_verdict BOOLEAN;
            v_omitted BOOLEAN;
        BEGIN
            v_verdict := fn_validation_check_amount(v_srcroot, v_omitted);
            IF NOT COALESCE(v_verdict, FALSE) THEN
                add_failed('input', 'AMOUNT_HIGH', 'amount above 10000', 'warn');
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_schema_failed_input THEN
                    add_failed('input', 'AMOUNT_HIGH', 'amount above 10000' || ' (the check could not be evaluated: ' || SQLERRM || ')', 'warn');
                END IF;
        END;
        IF v_rejected THEN
            DECLARE
                v_checks  JSON_ARRAY_T := JSON_ARRAY_T();
                v_check   JSON_OBJECT_T;
                v_payload JSON_OBJECT_T := JSON_OBJECT_T();
            BEGIN
                FOR v_i IN 0 .. v_report.get_size - 1 LOOP
                    v_check := JSON_OBJECT_T();
                    v_check.put('side', TREAT(v_report.get(v_i) AS JSON_OBJECT_T).get_string('side'));
                    v_check.put('code', TREAT(v_report.get(v_i) AS JSON_OBJECT_T).get_string('code'));
                    v_check.put('action', TREAT(v_report.get(v_i) AS JSON_OBJECT_T).get_string('action'));
                    v_checks.append(v_check);
                END LOOP;
                v_payload.put('mapping', 'validation');
                v_payload.put('rejected', TRUE);
                v_payload.put('checks', v_checks);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        DECLARE
            v_result_the_id VARCHAR2(4000 CHAR);
            v_omitted_the_id BOOLEAN;
        BEGIN
            v_result_the_id := fn_validation_the_id(v_srcroot, v_omitted_the_id);
            IF NOT v_omitted_the_id THEN
                v_out_obj.put('id', v_result_the_id);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('the_id') THEN
                    v_errors('the_id') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_the_amount NUMBER;
            v_omitted_the_amount BOOLEAN;
        BEGIN
            v_result_the_amount := fn_validation_the_amount(v_srcroot, v_omitted_the_amount);
            IF NOT v_omitted_the_amount THEN
                v_out_obj.put('amount', v_result_the_amount);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('the_amount') THEN
                    v_errors('the_amount') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_the_vat VARCHAR2(4000 CHAR);
            v_omitted_the_vat BOOLEAN;
        BEGIN
            v_result_the_vat := fn_validation_the_vat(v_srcroot, v_omitted_the_vat);
            IF NOT v_omitted_the_vat THEN
                v_out_obj.put('vat', v_result_the_vat);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('the_vat') THEN
                    v_errors('the_vat') := SQLERRM;
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
                v_payload.put('mapping', 'validation');
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
                v_payload.put('mapping', 'validation');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        DECLARE
            v_doc    CLOB := v_out_obj.TO_CLOB();
            v_schema CLOB := fn_validation_validation_schema_output;
            v_valid  NUMBER;
            v_paths  VARCHAR2(300);
            v_path   VARCHAR2(200);
            v_rep    VARCHAR2(4000);
            v_errs   JSON_ARRAY_T;
        BEGIN
            SELECT DBMS_JSON_SCHEMA.IS_VALID(JSON(v_doc), JSON(v_schema)) INTO v_valid FROM dual;
            IF v_valid = 0 THEN
                v_schema_failed_output := TRUE;
                BEGIN  -- where the document differs (the validator's own texts are not shipped)
                    SELECT JSON_QUERY(DBMS_JSON_SCHEMA.VALIDATE_REPORT(JSON(v_doc), JSON(v_schema)), '$.errors' RETURNING VARCHAR2(4000)) INTO v_rep FROM dual;
                    v_errs := JSON_ARRAY_T(v_rep);
                    FOR v_j IN 0 .. LEAST(v_errs.get_size, 6) - 1 LOOP
                        v_path := TREAT(v_errs.get(v_j) AS JSON_OBJECT_T).get_String('instancePath');
                        IF v_path <> '$' AND NVL(INSTR(v_paths, v_path), 0) = 0 AND NVL(LENGTH(v_paths), 0) < 200 THEN
                            v_paths := v_paths || CASE WHEN v_paths IS NULL THEN '' ELSE ', ' END || v_path;
                        END IF;
                    END LOOP;
                EXCEPTION WHEN OTHERS THEN NULL;
                END;
                add_failed('output', 'SCHEMA_OUTPUT', 'does not match the JSON Schema' || CASE WHEN v_paths IS NULL THEN '' ELSE ': ' || v_paths END, 'reject');
            END IF;
        END;
        DECLARE
            v_verdict BOOLEAN;
            v_omitted BOOLEAN;
        BEGIN
            v_verdict := fn_validation_check_positive(v_out_obj, v_omitted);
            IF NOT COALESCE(v_verdict, FALSE) THEN
                add_failed('output', 'OUT_POSITIVE', 'the amount must be positive', 'reject');
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_schema_failed_output THEN
                    add_failed('output', 'OUT_POSITIVE', 'the amount must be positive' || ' (the check could not be evaluated: ' || SQLERRM || ')', 'reject');
                END IF;
        END;
        IF v_rejected THEN
            DECLARE
                v_checks  JSON_ARRAY_T := JSON_ARRAY_T();
                v_check   JSON_OBJECT_T;
                v_payload JSON_OBJECT_T := JSON_OBJECT_T();
            BEGIN
                FOR v_i IN 0 .. v_report.get_size - 1 LOOP
                    v_check := JSON_OBJECT_T();
                    v_check.put('side', TREAT(v_report.get(v_i) AS JSON_OBJECT_T).get_string('side'));
                    v_check.put('code', TREAT(v_report.get(v_i) AS JSON_OBJECT_T).get_string('code'));
                    v_check.put('action', TREAT(v_report.get(v_i) AS JSON_OBJECT_T).get_string('action'));
                    v_checks.append(v_check);
                END LOOP;
                v_payload.put('mapping', 'validation');
                v_payload.put('rejected', TRUE);
                v_payload.put('checks', v_checks);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_validation;

    PROCEDURE map_validation_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB,
        p_report OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_report   JSON_ARRAY_T := JSON_ARRAY_T();
        v_rejected BOOLEAN := FALSE;
        v_schema_failed_input  BOOLEAN := FALSE;
        v_schema_failed_output BOOLEAN := FALSE;
        PROCEDURE add_failed(p_side IN VARCHAR2, p_code IN VARCHAR2, p_message IN VARCHAR2, p_action IN VARCHAR2) IS
            v_item JSON_OBJECT_T := JSON_OBJECT_T();
        BEGIN
            v_item.put('side', p_side);
            v_item.put('code', p_code);
            v_item.put('message', p_message);
            v_item.put('action', p_action);
            v_report.append(v_item);
            IF p_action = 'reject' THEN v_rejected := TRUE; END IF;
        END add_failed;
    BEGIN
        p_err := '[]';
        DECLARE
            v_doc    CLOB := p_src;
            v_schema CLOB := fn_validation_validation_schema_input;
            v_valid  NUMBER;
            v_paths  VARCHAR2(300);
            v_path   VARCHAR2(200);
            v_rep    VARCHAR2(4000);
            v_errs   JSON_ARRAY_T;
        BEGIN
            SELECT DBMS_JSON_SCHEMA.IS_VALID(JSON(v_doc), JSON(v_schema)) INTO v_valid FROM dual;
            IF v_valid = 0 THEN
                v_schema_failed_input := TRUE;
                BEGIN  -- where the document differs (the validator's own texts are not shipped)
                    SELECT JSON_QUERY(DBMS_JSON_SCHEMA.VALIDATE_REPORT(JSON(v_doc), JSON(v_schema)), '$.errors' RETURNING VARCHAR2(4000)) INTO v_rep FROM dual;
                    v_errs := JSON_ARRAY_T(v_rep);
                    FOR v_j IN 0 .. LEAST(v_errs.get_size, 6) - 1 LOOP
                        v_path := TREAT(v_errs.get(v_j) AS JSON_OBJECT_T).get_String('instancePath');
                        IF v_path <> '$' AND NVL(INSTR(v_paths, v_path), 0) = 0 AND NVL(LENGTH(v_paths), 0) < 200 THEN
                            v_paths := v_paths || CASE WHEN v_paths IS NULL THEN '' ELSE ', ' END || v_path;
                        END IF;
                    END LOOP;
                EXCEPTION WHEN OTHERS THEN NULL;
                END;
                add_failed('input', 'SCHEMA_INPUT', 'does not match the JSON Schema' || CASE WHEN v_paths IS NULL THEN '' ELSE ': ' || v_paths END, 'reject');
            END IF;
        END;
        DECLARE
            v_verdict BOOLEAN;
            v_omitted BOOLEAN;
        BEGIN
            v_verdict := fn_validation_check_vat(v_srcroot, v_omitted);
            IF NOT COALESCE(v_verdict, FALSE) THEN
                add_failed('input', 'VAT_FORMAT', 'vatId must be 11 digits', 'reject');
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_schema_failed_input THEN
                    add_failed('input', 'VAT_FORMAT', 'vatId must be 11 digits' || ' (the check could not be evaluated: ' || SQLERRM || ')', 'reject');
                END IF;
        END;
        DECLARE
            v_verdict BOOLEAN;
            v_omitted BOOLEAN;
        BEGIN
            v_verdict := fn_validation_check_amount(v_srcroot, v_omitted);
            IF NOT COALESCE(v_verdict, FALSE) THEN
                add_failed('input', 'AMOUNT_HIGH', 'amount above 10000', 'warn');
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_schema_failed_input THEN
                    add_failed('input', 'AMOUNT_HIGH', 'amount above 10000' || ' (the check could not be evaluated: ' || SQLERRM || ')', 'warn');
                END IF;
        END;
        IF NOT v_rejected THEN
            DECLARE
                v_result_the_id VARCHAR2(4000 CHAR);
                v_omitted_the_id BOOLEAN;
            BEGIN
                v_result_the_id := fn_validation_the_id(v_srcroot, v_omitted_the_id);
                IF NOT v_omitted_the_id THEN
                    v_out_obj.put('id', v_result_the_id);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('the_id') THEN
                        v_errors('the_id') := SQLERRM;
                    END IF;
            END;
            DECLARE
                v_result_the_amount NUMBER;
                v_omitted_the_amount BOOLEAN;
            BEGIN
                v_result_the_amount := fn_validation_the_amount(v_srcroot, v_omitted_the_amount);
                IF NOT v_omitted_the_amount THEN
                    v_out_obj.put('amount', v_result_the_amount);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('the_amount') THEN
                        v_errors('the_amount') := SQLERRM;
                    END IF;
            END;
            DECLARE
                v_result_the_vat VARCHAR2(4000 CHAR);
                v_omitted_the_vat BOOLEAN;
            BEGIN
                v_result_the_vat := fn_validation_the_vat(v_srcroot, v_omitted_the_vat);
                IF NOT v_omitted_the_vat THEN
                    v_out_obj.put('vat', v_result_the_vat);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('the_vat') THEN
                        v_errors('the_vat') := SQLERRM;
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
            DECLARE
                v_doc    CLOB := v_out_obj.TO_CLOB();
                v_schema CLOB := fn_validation_validation_schema_output;
                v_valid  NUMBER;
                v_paths  VARCHAR2(300);
                v_path   VARCHAR2(200);
                v_rep    VARCHAR2(4000);
                v_errs   JSON_ARRAY_T;
            BEGIN
                SELECT DBMS_JSON_SCHEMA.IS_VALID(JSON(v_doc), JSON(v_schema)) INTO v_valid FROM dual;
                IF v_valid = 0 THEN
                    v_schema_failed_output := TRUE;
                    BEGIN  -- where the document differs (the validator's own texts are not shipped)
                        SELECT JSON_QUERY(DBMS_JSON_SCHEMA.VALIDATE_REPORT(JSON(v_doc), JSON(v_schema)), '$.errors' RETURNING VARCHAR2(4000)) INTO v_rep FROM dual;
                        v_errs := JSON_ARRAY_T(v_rep);
                        FOR v_j IN 0 .. LEAST(v_errs.get_size, 6) - 1 LOOP
                            v_path := TREAT(v_errs.get(v_j) AS JSON_OBJECT_T).get_String('instancePath');
                            IF v_path <> '$' AND NVL(INSTR(v_paths, v_path), 0) = 0 AND NVL(LENGTH(v_paths), 0) < 200 THEN
                                v_paths := v_paths || CASE WHEN v_paths IS NULL THEN '' ELSE ', ' END || v_path;
                            END IF;
                        END LOOP;
                    EXCEPTION WHEN OTHERS THEN NULL;
                    END;
                    add_failed('output', 'SCHEMA_OUTPUT', 'does not match the JSON Schema' || CASE WHEN v_paths IS NULL THEN '' ELSE ': ' || v_paths END, 'reject');
                END IF;
            END;
            DECLARE
                v_verdict BOOLEAN;
                v_omitted BOOLEAN;
            BEGIN
                v_verdict := fn_validation_check_positive(v_out_obj, v_omitted);
                IF NOT COALESCE(v_verdict, FALSE) THEN
                    add_failed('output', 'OUT_POSITIVE', 'the amount must be positive', 'reject');
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_schema_failed_output THEN
                        add_failed('output', 'OUT_POSITIVE', 'the amount must be positive' || ' (the check could not be evaluated: ' || SQLERRM || ')', 'reject');
                    END IF;
            END;
        END IF;
        p_report := v_report.to_clob();
        IF v_rejected THEN p_out := NULL; ELSE p_out := v_out_obj.TO_CLOB(); END IF;
    END map_validation_safe;
END J2JME_MAP_VALIDATION;
/
