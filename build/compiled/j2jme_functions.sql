CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_FUNCTIONS AS
    FUNCTION lookup(p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;

    FUNCTION split_first(p_s IN VARCHAR2, p_sep IN VARCHAR2) RETURN VARCHAR2;

    FUNCTION split_nth(p_s IN VARCHAR2, p_sep IN VARCHAR2, p_n IN NUMBER) RETURN VARCHAR2;

    FUNCTION truthy(p_el IN JSON_ELEMENT_T) RETURN BOOLEAN;
END J2JME_FUNCTIONS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_FUNCTIONS AS
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

    FUNCTION truthy(p_el IN JSON_ELEMENT_T) RETURN BOOLEAN IS
    BEGIN
        IF p_el IS NULL OR p_el.is_Null THEN
            RETURN FALSE;
        ELSIF p_el.is_Boolean THEN
            RETURN COALESCE(p_el.to_Boolean, FALSE);
        ELSIF p_el.is_Number THEN
            RETURN COALESCE(p_el.to_Number, 0) <> 0;
        ELSIF p_el.is_String THEN
            RETURN p_el.to_String IS NOT NULL;
        ELSIF p_el.is_Array THEN
            RETURN TREAT(p_el AS JSON_ARRAY_T).get_size > 0;
        ELSIF p_el.is_Object THEN
            RETURN TREAT(p_el AS JSON_OBJECT_T).get_size > 0;
        END IF;
        RETURN TRUE;
    END truthy;
END J2JME_FUNCTIONS;
/
