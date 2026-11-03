CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_NULL_FORMS AS
    PROCEDURE map_null_forms (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_null_forms_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_NULL_FORMS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_NULL_FORMS AS
    FUNCTION fn_null_forms_none_rule(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_none_rule__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_none_rule__ret := p_root.get_String('missing');
        IF v_none_rule__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_none_rule__ret;
    END fn_null_forms_none_rule;

    FUNCTION fn_null_forms_null_rule(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN NULL;
    END fn_null_forms_null_rule;

    FUNCTION fn_null_forms_number_none(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_number_none__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_number_none__ret := (p_root.get_Number('n') + 1);
        IF v_number_none__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_number_none__ret;
    END fn_null_forms_number_none;

    FUNCTION fn_null_forms_box(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_box__dc JSON_OBJECT_T;
        v_val_box__v0 VARCHAR2(4000 CHAR);
        v_val_box__v1 VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_box__dc := JSON_OBJECT_T();
        v_val_box__v0 := 'k';
        IF v_val_box__v0 IS NOT NULL THEN
            v_box__dc.put('Kept', v_val_box__v0);
        END IF;
        v_val_box__v1 := p_root.get_String('missing');
        IF v_val_box__v1 IS NOT NULL THEN
            v_box__dc.put('Gone', v_val_box__v1);
        END IF;
        v_box__dc.put('Nulled', CAST(NULL AS NUMBER));
        RETURN v_box__dc;
    END fn_null_forms_box;

    FUNCTION fn_null_forms_biggest(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_biggest__agg NUMBER;
        v_aggarr_0 JSON_ARRAY_T;
        v_aggel_0 JSON_OBJECT_T;
        v_aggval_0 NUMBER;
        v_aggacc_0 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_0 := p_root.get_Array('items');
        v_aggacc_0 := NULL;
        IF v_aggarr_0 IS NOT NULL THEN
            FOR v_aggk_0 IN 0 .. v_aggarr_0.get_size - 1 LOOP
                v_aggel_0 := TREAT(v_aggarr_0.get(v_aggk_0) AS JSON_OBJECT_T);
                IF MAPPING_OWNER.J2JME_FUNCTIONS.truthy(v_aggel_0.get('ok')) THEN
                    v_aggval_0 := v_aggel_0.get_Number('v');
                    IF v_aggval_0 IS NOT NULL THEN
                        IF v_aggacc_0 IS NULL OR v_aggval_0 > v_aggacc_0 THEN v_aggacc_0 := v_aggval_0; END IF;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        v_biggest__agg := v_aggacc_0;
        IF v_biggest__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_biggest__agg;
    END fn_null_forms_biggest;

    FUNCTION fn_null_forms_total(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_total__agg NUMBER;
        v_aggarr_1 JSON_ARRAY_T;
        v_aggel_1 JSON_OBJECT_T;
        v_aggval_1 NUMBER;
        v_aggacc_1 NUMBER;
        v_aggn_1 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_1 := p_root.get_Array('items');
        v_aggacc_1 := 0;
        v_aggn_1 := 0;
        IF v_aggarr_1 IS NOT NULL THEN
            FOR v_aggk_1 IN 0 .. v_aggarr_1.get_size - 1 LOOP
                v_aggel_1 := TREAT(v_aggarr_1.get(v_aggk_1) AS JSON_OBJECT_T);
                IF MAPPING_OWNER.J2JME_FUNCTIONS.truthy(v_aggel_1.get('ok')) THEN
                    v_aggval_1 := v_aggel_1.get_Number('v');
                    IF v_aggval_1 IS NOT NULL THEN
                        v_aggacc_1 := v_aggacc_1 + v_aggval_1;
                        v_aggn_1 := v_aggn_1 + 1;
                    END IF;
                END IF;
            END LOOP;
        END IF;
        v_total__agg := v_aggacc_1;
        IF v_total__agg IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_total__agg;
    END fn_null_forms_total;

    FUNCTION fn_null_forms_looked(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_looked__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_looked__ret := MAPPING_OWNER.J2JME_FUNCTIONS.lookup(p_root.get_String('kind'), JSON_OBJECT_T('{}'), 'unknown');
        IF v_looked__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_looked__ret;
    END fn_null_forms_looked;

    PROCEDURE map_null_forms (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_none_rule VARCHAR2(4000 CHAR);
            v_omitted_none_rule BOOLEAN;
        BEGIN
            v_result_none_rule := fn_null_forms_none_rule(v_srcroot, v_omitted_none_rule);
            IF NOT v_omitted_none_rule THEN
                v_out_obj.put('NoneRule', v_result_none_rule);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('none_rule') THEN
                    v_errors('none_rule') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_null_rule VARCHAR2(4000 CHAR);
            v_omitted_null_rule BOOLEAN;
        BEGIN
            v_result_null_rule := fn_null_forms_null_rule(v_srcroot, v_omitted_null_rule);
            IF NOT v_omitted_null_rule THEN
                v_out_obj.put('NullRule', v_result_null_rule);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('null_rule') THEN
                    v_errors('null_rule') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_none NUMBER;
            v_omitted_number_none BOOLEAN;
        BEGIN
            v_result_number_none := fn_null_forms_number_none(v_srcroot, v_omitted_number_none);
            IF NOT v_omitted_number_none THEN
                v_out_obj.put('NumberNone', v_result_number_none);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_none') THEN
                    v_errors('number_none') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_val_o_Direct VARCHAR2(4000 CHAR);
        BEGIN
            v_val_o_Direct := v_srcroot.get_String('missing');
            IF v_val_o_Direct IS NOT NULL THEN
                v_out_obj.put('Direct', v_val_o_Direct);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('Direct') THEN
                    v_errors('Direct') := SQLERRM;
                END IF;
        END;
        BEGIN
            v_out_obj.put('DirectNull', CAST(NULL AS NUMBER));
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('DirectNull') THEN
                    v_errors('DirectNull') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_box JSON_OBJECT_T;
            v_omitted_box BOOLEAN;
        BEGIN
            v_result_box := fn_null_forms_box(v_srcroot, v_omitted_box);
            IF NOT v_omitted_box THEN
                v_out_obj.put('Box', v_result_box);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('box') THEN
                    v_errors('box') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_biggest NUMBER;
            v_omitted_biggest BOOLEAN;
        BEGIN
            v_result_biggest := fn_null_forms_biggest(v_srcroot, v_omitted_biggest);
            IF NOT v_omitted_biggest THEN
                v_out_obj.put('Biggest', v_result_biggest);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('biggest') THEN
                    v_errors('biggest') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_total NUMBER;
            v_omitted_total BOOLEAN;
        BEGIN
            v_result_total := fn_null_forms_total(v_srcroot, v_omitted_total);
            IF NOT v_omitted_total THEN
                v_out_obj.put('Total', v_result_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('total') THEN
                    v_errors('total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_looked VARCHAR2(4000 CHAR);
            v_omitted_looked BOOLEAN;
        BEGIN
            v_result_looked := fn_null_forms_looked(v_srcroot, v_omitted_looked);
            IF NOT v_omitted_looked THEN
                v_out_obj.put('Looked', v_result_looked);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('looked') THEN
                    v_errors('looked') := SQLERRM;
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
                v_payload.put('mapping', 'null_forms');
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
                v_payload.put('mapping', 'null_forms');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_null_forms;

    PROCEDURE map_null_forms_safe (
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
            v_result_none_rule VARCHAR2(4000 CHAR);
            v_omitted_none_rule BOOLEAN;
        BEGIN
            v_result_none_rule := fn_null_forms_none_rule(v_srcroot, v_omitted_none_rule);
            IF NOT v_omitted_none_rule THEN
                v_out_obj.put('NoneRule', v_result_none_rule);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('none_rule') THEN
                    v_errors('none_rule') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_null_rule VARCHAR2(4000 CHAR);
            v_omitted_null_rule BOOLEAN;
        BEGIN
            v_result_null_rule := fn_null_forms_null_rule(v_srcroot, v_omitted_null_rule);
            IF NOT v_omitted_null_rule THEN
                v_out_obj.put('NullRule', v_result_null_rule);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('null_rule') THEN
                    v_errors('null_rule') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_number_none NUMBER;
            v_omitted_number_none BOOLEAN;
        BEGIN
            v_result_number_none := fn_null_forms_number_none(v_srcroot, v_omitted_number_none);
            IF NOT v_omitted_number_none THEN
                v_out_obj.put('NumberNone', v_result_number_none);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('number_none') THEN
                    v_errors('number_none') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_val_o_Direct VARCHAR2(4000 CHAR);
        BEGIN
            v_val_o_Direct := v_srcroot.get_String('missing');
            IF v_val_o_Direct IS NOT NULL THEN
                v_out_obj.put('Direct', v_val_o_Direct);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('Direct') THEN
                    v_errors('Direct') := SQLERRM;
                END IF;
        END;
        BEGIN
            v_out_obj.put('DirectNull', CAST(NULL AS NUMBER));
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('DirectNull') THEN
                    v_errors('DirectNull') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_box JSON_OBJECT_T;
            v_omitted_box BOOLEAN;
        BEGIN
            v_result_box := fn_null_forms_box(v_srcroot, v_omitted_box);
            IF NOT v_omitted_box THEN
                v_out_obj.put('Box', v_result_box);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('box') THEN
                    v_errors('box') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_biggest NUMBER;
            v_omitted_biggest BOOLEAN;
        BEGIN
            v_result_biggest := fn_null_forms_biggest(v_srcroot, v_omitted_biggest);
            IF NOT v_omitted_biggest THEN
                v_out_obj.put('Biggest', v_result_biggest);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('biggest') THEN
                    v_errors('biggest') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_total NUMBER;
            v_omitted_total BOOLEAN;
        BEGIN
            v_result_total := fn_null_forms_total(v_srcroot, v_omitted_total);
            IF NOT v_omitted_total THEN
                v_out_obj.put('Total', v_result_total);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('total') THEN
                    v_errors('total') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_looked VARCHAR2(4000 CHAR);
            v_omitted_looked BOOLEAN;
        BEGIN
            v_result_looked := fn_null_forms_looked(v_srcroot, v_omitted_looked);
            IF NOT v_omitted_looked THEN
                v_out_obj.put('Looked', v_result_looked);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('looked') THEN
                    v_errors('looked') := SQLERRM;
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
    END map_null_forms_safe;
END J2JME_MAP_NULL_FORMS;
/
