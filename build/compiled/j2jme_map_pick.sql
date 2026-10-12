CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_PICK AS
    PROCEDURE map_pick (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_pick_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_PICK;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_PICK AS
    FUNCTION fn_pick_pick_items(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_pick_items_found JSON_ARRAY_T;
        v_forarr_0 JSON_ARRAY_T;
        v_pick_items_item JSON_OBJECT_T;
    BEGIN
        p_omitted := FALSE;
        v_pick_items_found := JSON_ARRAY_T();
        v_forarr_0 := p_root.get_Array('items');
        IF v_forarr_0 IS NOT NULL THEN
            FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
                v_pick_items_item := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
                IF (v_pick_items_item.get_String('marker') = 'TOTALS') THEN
                    v_pick_items_found.append(v_pick_items_item);
                END IF;
            END LOOP;
        END IF;
        IF (v_pick_items_found IS NOT NULL AND v_pick_items_found.get_size > 0) THEN
            RETURN TREAT(v_pick_items_found.get(0) AS JSON_OBJECT_T);
        END IF;
        RETURN JSON_OBJECT_T('{}');
    END fn_pick_pick_items;

    FUNCTION fn_pick_pick_nope(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_pick_nope_found JSON_ARRAY_T;
        v_forarr_1 JSON_ARRAY_T;
        v_pick_nope_item JSON_OBJECT_T;
    BEGIN
        p_omitted := FALSE;
        v_pick_nope_found := JSON_ARRAY_T();
        v_forarr_1 := p_root.get_Array('items');
        IF v_forarr_1 IS NOT NULL THEN
            FOR v_i_1 IN 0 .. v_forarr_1.get_size - 1 LOOP
                v_pick_nope_item := TREAT(v_forarr_1.get(v_i_1) AS JSON_OBJECT_T);
                IF (v_pick_nope_item.get_String('marker') = 'NOPE') THEN
                    v_pick_nope_found.append(v_pick_nope_item);
                END IF;
            END LOOP;
        END IF;
        IF (v_pick_nope_found IS NOT NULL AND v_pick_nope_found.get_size > 0) THEN
            RETURN TREAT(v_pick_nope_found.get(0) AS JSON_OBJECT_T);
        END IF;
        RETURN JSON_OBJECT_T('{}');
    END fn_pick_pick_nope;

    FUNCTION fn_pick_pick_prices(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_pick_prices_found JSON_ARRAY_T;
        v_forarr_2 JSON_ARRAY_T;
        v_pick_prices_price JSON_OBJECT_T;
    BEGIN
        p_omitted := FALSE;
        v_pick_prices_found := JSON_ARRAY_T();
        v_forarr_2 := p_root.get_Array('prices');
        IF v_forarr_2 IS NOT NULL THEN
            FOR v_i_2 IN 0 .. v_forarr_2.get_size - 1 LOOP
                v_pick_prices_price := TREAT(v_forarr_2.get(v_i_2) AS JSON_OBJECT_T);
                IF (v_pick_prices_price.get_String('sku') = p_src.get_String('sku')) THEN
                    v_pick_prices_found.append(v_pick_prices_price);
                END IF;
            END LOOP;
        END IF;
        IF (v_pick_prices_found IS NOT NULL AND v_pick_prices_found.get_size > 0) THEN
            RETURN TREAT(v_pick_prices_found.get(0) AS JSON_OBJECT_T);
        END IF;
        RETURN JSON_OBJECT_T('{}');
    END fn_pick_pick_prices;

    FUNCTION fn_pick_total(p_root IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_total_total_items_pick JSON_OBJECT_T;
        v_total_total_items_pick__o BOOLEAN;
        v_total__ret NUMBER;
    BEGIN
        p_omitted := FALSE;
        BEGIN
            v_total_total_items_pick := fn_pick_pick_items(p_root, v_total_total_items_pick__o);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT p__errors.has('pick_items') THEN
                    p__errors.put('pick_items', SQLERRM);
                END IF;
                v_total_total_items_pick__o := TRUE;
        END;
        v_total__ret := v_total_total_items_pick.get_Number('qty');
        IF v_total__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_total__ret;
    END fn_pick_total;

    FUNCTION fn_pick_currency(p_root IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_currency_currency_items_pick JSON_OBJECT_T;
        v_currency_currency_items_pick__o BOOLEAN;
        v_currency__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        BEGIN
            v_currency_currency_items_pick := fn_pick_pick_items(p_root, v_currency_currency_items_pick__o);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT p__errors.has('pick_items') THEN
                    p__errors.put('pick_items', SQLERRM);
                END IF;
                v_currency_currency_items_pick__o := TRUE;
        END;
        v_currency__ret := v_currency_currency_items_pick.get_String('cur');
        IF v_currency__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_currency__ret;
    END fn_pick_currency;

    FUNCTION fn_pick_missing(p_root IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_missing_missing_items_pick JSON_OBJECT_T;
        v_missing_missing_items_pick__o BOOLEAN;
        v_missing__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        BEGIN
            v_missing_missing_items_pick := fn_pick_pick_nope(p_root, v_missing_missing_items_pick__o);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT p__errors.has('pick_nope') THEN
                    p__errors.put('pick_nope', SQLERRM);
                END IF;
                v_missing_missing_items_pick__o := TRUE;
        END;
        v_missing__ret := v_missing_missing_items_pick.get_String('cur');
        IF v_missing__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_missing__ret;
    END fn_pick_missing;

    FUNCTION fn_pick_line(p_root IN JSON_OBJECT_T, p_src IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_line_line_prices_pick JSON_OBJECT_T;
        v_line_line_prices_pick__o BOOLEAN;
        v_line__dc JSON_OBJECT_T;
        v_val_line__v0 VARCHAR2(4000 CHAR);
        v_val_line__v1 NUMBER;
    BEGIN
        p_omitted := FALSE;
        BEGIN
            v_line_line_prices_pick := fn_pick_pick_prices(p_root, p_src, v_line_line_prices_pick__o);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT p__errors.has('pick_prices') THEN
                    p__errors.put('pick_prices', SQLERRM);
                END IF;
                v_line_line_prices_pick__o := TRUE;
        END;
        v_line__dc := JSON_OBJECT_T();
        v_val_line__v0 := p_src.get_String('sku');
        IF v_val_line__v0 IS NOT NULL THEN
            v_line__dc.put('Sku', v_val_line__v0);
        END IF;
        v_val_line__v1 := v_line_line_prices_pick.get_Number('price');
        IF v_val_line__v1 IS NOT NULL THEN
            v_line__dc.put('Price', v_val_line__v1);
        END IF;
        RETURN v_line__dc;
    END fn_pick_line;

    PROCEDURE map_pick (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
        v_arr_Lines JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_result_total NUMBER;
            v_omitted_total BOOLEAN;
        BEGIN
            v_result_total := fn_pick_total(v_srcroot, v_rule_errors, v_omitted_total);
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
            v_result_currency VARCHAR2(4000 CHAR);
            v_omitted_currency BOOLEAN;
        BEGIN
            v_result_currency := fn_pick_currency(v_srcroot, v_rule_errors, v_omitted_currency);
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
            v_result_missing VARCHAR2(4000 CHAR);
            v_omitted_missing BOOLEAN;
        BEGIN
            v_result_missing := fn_pick_missing(v_srcroot, v_rule_errors, v_omitted_missing);
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
            v_forarr_3 JSON_ARRAY_T := v_srcroot.get_Array('lines');
        BEGIN
            IF v_forarr_3 IS NOT NULL THEN
                FOR v_i_3 IN 0 .. v_forarr_3.get_size - 1 LOOP
                    DECLARE
                        v_src JSON_OBJECT_T := TREAT(v_forarr_3.get(v_i_3) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_line JSON_OBJECT_T;
                            v_omitted_line BOOLEAN;
                        BEGIN
                            v_result_line := fn_pick_line(v_srcroot, v_src, v_rule_errors, v_omitted_line);
                            IF NOT v_omitted_line THEN
                                v_arr_Lines.append(v_result_line);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('line') THEN
                                    v_errors('line') := SQLERRM;
                                END IF;
                        END;
                    END;
                END LOOP;
            END IF;
        END;

        DECLARE
            v_rule_keys JSON_KEY_LIST := v_rule_errors.get_keys;
        BEGIN
            FOR v_k IN 1 .. v_rule_keys.COUNT LOOP
                IF NOT v_errors.EXISTS(v_rule_keys(v_k)) THEN
                    v_errors(v_rule_keys(v_k)) := v_rule_errors.get_String(v_rule_keys(v_k));
                END IF;
            END LOOP;
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
                v_payload.put('mapping', 'pick');
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
                v_payload.put('mapping', 'pick');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        v_out_obj.put('Lines', v_arr_Lines);
        p_out := v_out_obj.TO_CLOB();
    END map_pick;

    PROCEDURE map_pick_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
        v_arr_Lines JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_result_total NUMBER;
            v_omitted_total BOOLEAN;
        BEGIN
            v_result_total := fn_pick_total(v_srcroot, v_rule_errors, v_omitted_total);
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
            v_result_currency VARCHAR2(4000 CHAR);
            v_omitted_currency BOOLEAN;
        BEGIN
            v_result_currency := fn_pick_currency(v_srcroot, v_rule_errors, v_omitted_currency);
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
            v_result_missing VARCHAR2(4000 CHAR);
            v_omitted_missing BOOLEAN;
        BEGIN
            v_result_missing := fn_pick_missing(v_srcroot, v_rule_errors, v_omitted_missing);
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
            v_forarr_3 JSON_ARRAY_T := v_srcroot.get_Array('lines');
        BEGIN
            IF v_forarr_3 IS NOT NULL THEN
                FOR v_i_3 IN 0 .. v_forarr_3.get_size - 1 LOOP
                    DECLARE
                        v_src JSON_OBJECT_T := TREAT(v_forarr_3.get(v_i_3) AS JSON_OBJECT_T);
                    BEGIN
                        DECLARE
                            v_result_line JSON_OBJECT_T;
                            v_omitted_line BOOLEAN;
                        BEGIN
                            v_result_line := fn_pick_line(v_srcroot, v_src, v_rule_errors, v_omitted_line);
                            IF NOT v_omitted_line THEN
                                v_arr_Lines.append(v_result_line);
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN
                                IF NOT v_errors.EXISTS('line') THEN
                                    v_errors('line') := SQLERRM;
                                END IF;
                        END;
                    END;
                END LOOP;
            END IF;
        END;

        DECLARE
            v_rule_keys JSON_KEY_LIST := v_rule_errors.get_keys;
        BEGIN
            FOR v_k IN 1 .. v_rule_keys.COUNT LOOP
                IF NOT v_errors.EXISTS(v_rule_keys(v_k)) THEN
                    v_errors(v_rule_keys(v_k)) := v_rule_errors.get_String(v_rule_keys(v_k));
                END IF;
            END LOOP;
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
        v_out_obj.put('Lines', v_arr_Lines);
        p_out := v_out_obj.TO_CLOB();
    END map_pick_safe;
END J2JME_MAP_PICK;
/
