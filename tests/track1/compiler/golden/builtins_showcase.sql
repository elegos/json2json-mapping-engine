CREATE OR REPLACE PACKAGE J2JME_FUNCTIONS AS
    FUNCTION lookup(p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;

    FUNCTION split_first(p_s IN VARCHAR2, p_sep IN VARCHAR2) RETURN VARCHAR2;

    FUNCTION split_nth(p_s IN VARCHAR2, p_sep IN VARCHAR2, p_n IN NUMBER) RETURN VARCHAR2;
END J2JME_FUNCTIONS;
/

CREATE OR REPLACE PACKAGE BODY J2JME_FUNCTIONS AS
    FUNCTION lookup(p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
    BEGIN
        RETURN (CASE WHEN p_table.has(p_key) THEN p_table.get_String(p_key) ELSE p_default END);
    END lookup;

    FUNCTION split_first(p_s IN VARCHAR2, p_sep IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN SUBSTR(p_s, 1, INSTR(p_s || p_sep, p_sep) - 1);
    END split_first;

    FUNCTION split_nth(p_s IN VARCHAR2, p_sep IN VARCHAR2, p_n IN NUMBER) RETURN VARCHAR2 IS
    BEGIN
        RETURN (CASE WHEN INSTR((p_s || p_sep), p_sep, 1, p_n) = 0 THEN NULL ELSE SUBSTR((p_s || p_sep), INSTR((p_s || p_sep), p_sep, 1, p_n - 1) + LENGTH(p_sep), INSTR((p_s || p_sep), p_sep, 1, p_n) - INSTR((p_s || p_sep), p_sep, 1, p_n - 1) - LENGTH(p_sep)) END);
    END split_nth;
END J2JME_FUNCTIONS;
/

CREATE OR REPLACE PACKAGE BUILTINS_SHOWCASE AS
    PROCEDURE map_builtins_showcase (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_showcase_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END BUILTINS_SHOWCASE;
/

CREATE OR REPLACE PACKAGE BODY BUILTINS_SHOWCASE AS
    FUNCTION fn_builtins_showcase_rounded_amount(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN ROUND(p_root.get_Number('amount'), 2);
    END fn_builtins_showcase_rounded_amount;

    FUNCTION fn_builtins_showcase_full_name(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (p_root.get_String('firstName') || ' ' || p_root.get_String('lastName'));
    END fn_builtins_showcase_full_name;

    FUNCTION fn_builtins_showcase_tier_label(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN (p_root.get_Number('score') >= 90) THEN 'GOLD' ELSE 'STANDARD' END);
    END fn_builtins_showcase_tier_label;

    FUNCTION fn_builtins_showcase_ref_first(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN J2JME_FUNCTIONS.split_first(p_root.get_String('ref'), '|');
    END fn_builtins_showcase_ref_first;

    FUNCTION fn_builtins_showcase_ref_second(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN J2JME_FUNCTIONS.split_nth(p_root.get_String('ref'), '|', 2);
    END fn_builtins_showcase_ref_second;

    FUNCTION fn_builtins_showcase_currency(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN J2JME_FUNCTIONS.lookup(p_root.get_String('countryCode'), p_root.get_Object('currencyTable'), 'EUR');
    END fn_builtins_showcase_currency;

    FUNCTION fn_builtins_showcase_shipped_on(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN DATE IS
    BEGIN
        p_omitted := FALSE;
        RETURN TO_DATE(p_root.get_String('shippedOn'), 'YYYY-MM-DD');
    END fn_builtins_showcase_shipped_on;

    PROCEDURE map_builtins_showcase (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_rounded_amount NUMBER;
            v_omitted_rounded_amount BOOLEAN;
        BEGIN
            v_result_rounded_amount := fn_builtins_showcase_rounded_amount(v_srcroot, v_omitted_rounded_amount);
            IF NOT v_omitted_rounded_amount THEN
                v_out_obj.put('RoundedAmount', v_result_rounded_amount);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rounded_amount') THEN
                    v_errors('rounded_amount') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_full_name VARCHAR2(4000 CHAR);
            v_omitted_full_name BOOLEAN;
        BEGIN
            v_result_full_name := fn_builtins_showcase_full_name(v_srcroot, v_omitted_full_name);
            IF NOT v_omitted_full_name THEN
                v_out_obj.put('FullName', v_result_full_name);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('full_name') THEN
                    v_errors('full_name') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_tier_label VARCHAR2(4000 CHAR);
            v_omitted_tier_label BOOLEAN;
        BEGIN
            v_result_tier_label := fn_builtins_showcase_tier_label(v_srcroot, v_omitted_tier_label);
            IF NOT v_omitted_tier_label THEN
                v_out_obj.put('TierLabel', v_result_tier_label);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('tier_label') THEN
                    v_errors('tier_label') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ref_first VARCHAR2(4000 CHAR);
            v_omitted_ref_first BOOLEAN;
        BEGIN
            v_result_ref_first := fn_builtins_showcase_ref_first(v_srcroot, v_omitted_ref_first);
            IF NOT v_omitted_ref_first THEN
                v_out_obj.put('RefFirst', v_result_ref_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ref_first') THEN
                    v_errors('ref_first') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ref_second VARCHAR2(4000 CHAR);
            v_omitted_ref_second BOOLEAN;
        BEGIN
            v_result_ref_second := fn_builtins_showcase_ref_second(v_srcroot, v_omitted_ref_second);
            IF NOT v_omitted_ref_second THEN
                v_out_obj.put('RefSecond', v_result_ref_second);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ref_second') THEN
                    v_errors('ref_second') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_currency VARCHAR2(4000 CHAR);
            v_omitted_currency BOOLEAN;
        BEGIN
            v_result_currency := fn_builtins_showcase_currency(v_srcroot, v_omitted_currency);
            IF NOT v_omitted_currency THEN
                v_out_obj.put('Currency', v_result_currency);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('currency') THEN
                    v_errors('currency') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_shipped_on DATE;
            v_omitted_shipped_on BOOLEAN;
        BEGIN
            v_result_shipped_on := fn_builtins_showcase_shipped_on(v_srcroot, v_omitted_shipped_on);
            IF NOT v_omitted_shipped_on THEN
                v_out_obj.put('ShippedOn', v_result_shipped_on);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('shipped_on') THEN
                    v_errors('shipped_on') := SQLERRM;
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
                v_payload.put('mapping', 'builtins_showcase');
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
                v_payload.put('mapping', 'builtins_showcase');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_builtins_showcase;

    PROCEDURE map_builtins_showcase_safe (
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
            v_result_rounded_amount NUMBER;
            v_omitted_rounded_amount BOOLEAN;
        BEGIN
            v_result_rounded_amount := fn_builtins_showcase_rounded_amount(v_srcroot, v_omitted_rounded_amount);
            IF NOT v_omitted_rounded_amount THEN
                v_out_obj.put('RoundedAmount', v_result_rounded_amount);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('rounded_amount') THEN
                    v_errors('rounded_amount') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_full_name VARCHAR2(4000 CHAR);
            v_omitted_full_name BOOLEAN;
        BEGIN
            v_result_full_name := fn_builtins_showcase_full_name(v_srcroot, v_omitted_full_name);
            IF NOT v_omitted_full_name THEN
                v_out_obj.put('FullName', v_result_full_name);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('full_name') THEN
                    v_errors('full_name') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_tier_label VARCHAR2(4000 CHAR);
            v_omitted_tier_label BOOLEAN;
        BEGIN
            v_result_tier_label := fn_builtins_showcase_tier_label(v_srcroot, v_omitted_tier_label);
            IF NOT v_omitted_tier_label THEN
                v_out_obj.put('TierLabel', v_result_tier_label);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('tier_label') THEN
                    v_errors('tier_label') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ref_first VARCHAR2(4000 CHAR);
            v_omitted_ref_first BOOLEAN;
        BEGIN
            v_result_ref_first := fn_builtins_showcase_ref_first(v_srcroot, v_omitted_ref_first);
            IF NOT v_omitted_ref_first THEN
                v_out_obj.put('RefFirst', v_result_ref_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ref_first') THEN
                    v_errors('ref_first') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_ref_second VARCHAR2(4000 CHAR);
            v_omitted_ref_second BOOLEAN;
        BEGIN
            v_result_ref_second := fn_builtins_showcase_ref_second(v_srcroot, v_omitted_ref_second);
            IF NOT v_omitted_ref_second THEN
                v_out_obj.put('RefSecond', v_result_ref_second);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ref_second') THEN
                    v_errors('ref_second') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_currency VARCHAR2(4000 CHAR);
            v_omitted_currency BOOLEAN;
        BEGIN
            v_result_currency := fn_builtins_showcase_currency(v_srcroot, v_omitted_currency);
            IF NOT v_omitted_currency THEN
                v_out_obj.put('Currency', v_result_currency);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('currency') THEN
                    v_errors('currency') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_shipped_on DATE;
            v_omitted_shipped_on BOOLEAN;
        BEGIN
            v_result_shipped_on := fn_builtins_showcase_shipped_on(v_srcroot, v_omitted_shipped_on);
            IF NOT v_omitted_shipped_on THEN
                v_out_obj.put('ShippedOn', v_result_shipped_on);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('shipped_on') THEN
                    v_errors('shipped_on') := SQLERRM;
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
    END map_builtins_showcase_safe;
END BUILTINS_SHOWCASE;
/
