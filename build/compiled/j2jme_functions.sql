CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_FUNCTIONS AS
    FUNCTION format_decimal(p_x IN NUMBER, p_n IN NUMBER) RETURN VARCHAR2;

    FUNCTION lookup(p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;

    FUNCTION remove_prefix(p_s IN VARCHAR2, p_prefix IN VARCHAR2) RETURN VARCHAR2;

    FUNCTION rfc3339_normalize(p_s IN VARCHAR2) RETURN VARCHAR2;

    FUNCTION split_first(p_s IN VARCHAR2, p_sep IN VARCHAR2) RETURN VARCHAR2;

    FUNCTION split_nth(p_s IN VARCHAR2, p_sep IN VARCHAR2, p_n IN NUMBER) RETURN VARCHAR2;

    FUNCTION to_number(p_el IN JSON_ELEMENT_T) RETURN NUMBER;

    FUNCTION to_string(p_el IN JSON_ELEMENT_T) RETURN VARCHAR2;

    FUNCTION to_utc(p_s IN VARCHAR2) RETURN VARCHAR2;

    FUNCTION truthy(p_el IN JSON_ELEMENT_T) RETURN BOOLEAN;
END J2JME_FUNCTIONS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_FUNCTIONS AS
    FUNCTION format_decimal(p_x IN NUMBER, p_n IN NUMBER) RETURN VARCHAR2 IS
    BEGIN
        IF p_x IS NULL THEN
            RETURN NULL;
        END IF;
        IF p_n < 0 THEN
            RAISE_APPLICATION_ERROR(-20999, 'the number of decimals cannot be negative');
        END IF;
        RETURN TRIM(TO_CHAR(ROUND(p_x, p_n), 'FM999999999999999999990' || CASE WHEN p_n > 0 THEN '.' || RPAD('0', p_n, '0') END, 'NLS_NUMERIC_CHARACTERS=''.,'''));
    END format_decimal;

    FUNCTION lookup(p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2 IS
    BEGIN
        RETURN (CASE WHEN p_table.has(p_key) THEN p_table.get_String(p_key) ELSE p_default END);
    END lookup;

    FUNCTION remove_prefix(p_s IN VARCHAR2, p_prefix IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN (CASE WHEN p_prefix IS NOT NULL AND SUBSTR(p_s, 1, LENGTH(p_prefix)) = p_prefix THEN SUBSTR(p_s, LENGTH(p_prefix) + 1) ELSE p_s END);
    END remove_prefix;

    FUNCTION rfc3339_normalize(p_s IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        DECLARE
            v_date VARCHAR2(10) := REGEXP_SUBSTR(p_s, '^\s*(\d{4}-\d{2}-\d{2})', 1, 1, NULL, 1);
            v_time VARCHAR2(8);
            v_frac VARCHAR2(9);
            v_zone VARCHAR2(10);
        BEGIN
            IF p_s IS NULL THEN
                RETURN NULL;
            END IF;
            IF v_date IS NULL THEN
                RAISE_APPLICATION_ERROR(-20999, 'not an ISO-8601 / RFC3339 timestamp: ' || p_s);
            END IF;
            v_time := NVL(REGEXP_SUBSTR(p_s, '[T ](\d{2}:\d{2}(:\d{2})?)', 1, 1, 'i', 1), '00:00');
            IF LENGTH(v_time) = 5 THEN
                v_time := v_time || ':00';
            END IF;
            v_frac := REGEXP_SUBSTR(p_s, '\d{2}:\d{2}:\d{2}[.,](\d{1,9})', 1, 1, NULL, 1);
            v_zone := REGEXP_SUBSTR(p_s,
                '\d{2}:\d{2}(:\d{2}([.,]\d{1,9})?)?\s*(Z|[+-]\d{2}(:?\d{2})?)\s*$', 1, 1, 'i', 3);
            v_zone := CASE
                WHEN v_zone IS NULL OR UPPER(v_zone) = 'Z' THEN '+00:00'
                WHEN LENGTH(v_zone) = 3 THEN v_zone || ':00'
                WHEN LENGTH(v_zone) = 5 THEN SUBSTR(v_zone, 1, 3) || ':' || SUBSTR(v_zone, 4)
                ELSE v_zone END;
            v_date := TO_CHAR(TO_DATE(v_date, 'YYYY-MM-DD'), 'YYYY-MM-DD'); -- an invalid date raises
            RETURN v_date || 'T' || v_time || CASE WHEN v_frac IS NOT NULL THEN '.' || v_frac END
                || CASE WHEN v_zone = '+00:00' THEN 'Z' ELSE v_zone END;
        END;
    END rfc3339_normalize;

    FUNCTION split_first(p_s IN VARCHAR2, p_sep IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        RETURN SUBSTR(p_s, 1, INSTR(p_s || p_sep, p_sep) - 1);
    END split_first;

    FUNCTION split_nth(p_s IN VARCHAR2, p_sep IN VARCHAR2, p_n IN NUMBER) RETURN VARCHAR2 IS
    BEGIN
        RETURN (CASE WHEN INSTR((p_s || p_sep), p_sep, 1, p_n) = 0 THEN NULL ELSE SUBSTR((p_s || p_sep), INSTR((p_s || p_sep), p_sep, 1, p_n - 1) + LENGTH(p_sep), INSTR((p_s || p_sep), p_sep, 1, p_n) - INSTR((p_s || p_sep), p_sep, 1, p_n - 1) - LENGTH(p_sep)) END);
    END split_nth;

    FUNCTION to_number(p_el IN JSON_ELEMENT_T) RETURN NUMBER IS
    BEGIN
        IF p_el IS NULL OR p_el.is_Null THEN
            RETURN NULL;
        ELSIF p_el.is_Number THEN
            RETURN p_el.to_Number;
        ELSIF p_el.is_String THEN
            RETURN TO_NUMBER(TRIM(JSON_VALUE(p_el.to_String, '$' RETURNING VARCHAR2(4000))), '99999999999999999999999999999999D99999999999999999999', 'NLS_NUMERIC_CHARACTERS=''.,''');
        END IF;
        RAISE_APPLICATION_ERROR(-20999, 'not a number: ' || p_el.to_String);
    END to_number;

    FUNCTION to_string(p_el IN JSON_ELEMENT_T) RETURN VARCHAR2 IS
    BEGIN
        IF p_el IS NULL OR p_el.is_Null THEN
            RETURN NULL;
        ELSIF p_el.is_Number THEN
            RETURN TO_CHAR(p_el.to_Number, 'TM9', 'NLS_NUMERIC_CHARACTERS=''.,''');
        ELSIF p_el.is_Boolean THEN
            RETURN (CASE WHEN p_el.to_Boolean THEN 'true' WHEN NOT p_el.to_Boolean THEN 'false' END);
        ELSIF p_el.is_String THEN
            -- to_String is the JSON text, quotes and escapes included: read the value out of it
            RETURN JSON_VALUE(p_el.to_String, '$' RETURNING VARCHAR2(4000));
        END IF;
        RETURN p_el.to_String;
    END to_string;

    FUNCTION to_utc(p_s IN VARCHAR2) RETURN VARCHAR2 IS
    BEGIN
        DECLARE
            v_date VARCHAR2(10) := REGEXP_SUBSTR(p_s, '^\s*(\d{4}-\d{2}-\d{2})', 1, 1, NULL, 1);
            v_time VARCHAR2(8);
            v_frac VARCHAR2(9);
            v_zone VARCHAR2(10);
        BEGIN
            IF p_s IS NULL THEN
                RETURN NULL;
            END IF;
            IF v_date IS NULL THEN
                RAISE_APPLICATION_ERROR(-20999, 'not an ISO-8601 / RFC3339 timestamp: ' || p_s);
            END IF;
            v_time := NVL(REGEXP_SUBSTR(p_s, '[T ](\d{2}:\d{2}(:\d{2})?)', 1, 1, 'i', 1), '00:00');
            IF LENGTH(v_time) = 5 THEN
                v_time := v_time || ':00';
            END IF;
            v_frac := REGEXP_SUBSTR(p_s, '\d{2}:\d{2}:\d{2}[.,](\d{1,9})', 1, 1, NULL, 1);
            v_zone := REGEXP_SUBSTR(p_s,
                '\d{2}:\d{2}(:\d{2}([.,]\d{1,9})?)?\s*(Z|[+-]\d{2}(:?\d{2})?)\s*$', 1, 1, 'i', 3);
            v_zone := CASE
                WHEN v_zone IS NULL OR UPPER(v_zone) = 'Z' THEN '+00:00'
                WHEN LENGTH(v_zone) = 3 THEN v_zone || ':00'
                WHEN LENGTH(v_zone) = 5 THEN SUBSTR(v_zone, 1, 3) || ':' || SUBSTR(v_zone, 4)
                ELSE v_zone END;
            v_date := TO_CHAR(TO_DATE(v_date, 'YYYY-MM-DD'), 'YYYY-MM-DD'); -- an invalid date raises
            RETURN TO_CHAR(SYS_EXTRACT_UTC(TO_TIMESTAMP_TZ(v_date || 'T' || v_time || v_zone,
                    'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM')), 'YYYY-MM-DD"T"HH24:MI:SS')
                || CASE WHEN v_frac IS NOT NULL THEN '.' || v_frac END || 'Z';
        END;
    END to_utc;

    FUNCTION truthy(p_el IN JSON_ELEMENT_T) RETURN BOOLEAN IS
    BEGIN
        IF p_el IS NULL OR p_el.is_Null THEN
            RETURN FALSE;
        ELSIF p_el.is_Boolean THEN
            RETURN COALESCE(p_el.to_Boolean, FALSE);
        ELSIF p_el.is_Number THEN
            RETURN COALESCE(p_el.to_Number, 0) <> 0;
        ELSIF p_el.is_String THEN
            -- to_String is the JSON text, quotes included: the empty string is '""', not NULL
            RETURN p_el.to_String <> '""';
        ELSIF p_el.is_Array THEN
            RETURN TREAT(p_el AS JSON_ARRAY_T).get_size > 0;
        ELSIF p_el.is_Object THEN
            RETURN TREAT(p_el AS JSON_OBJECT_T).get_size > 0;
        END IF;
        RETURN TRUE;
    END truthy;
END J2JME_FUNCTIONS;
/
