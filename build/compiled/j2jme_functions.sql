CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_FUNCTIONS AS
    FUNCTION lookup(p_key IN VARCHAR2, p_table IN JSON_OBJECT_T, p_default IN VARCHAR2 DEFAULT NULL) RETURN VARCHAR2;

    FUNCTION split_first(p_s IN VARCHAR2, p_sep IN VARCHAR2) RETURN VARCHAR2;

    FUNCTION split_nth(p_s IN VARCHAR2, p_sep IN VARCHAR2, p_n IN NUMBER) RETURN VARCHAR2;
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
END J2JME_FUNCTIONS;
/
