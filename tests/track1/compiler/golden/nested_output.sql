CREATE OR REPLACE PACKAGE NESTED_OUTPUT AS
    PROCEDURE map_nested_output (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_nested_output_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END NESTED_OUTPUT;
/

CREATE OR REPLACE PACKAGE BODY NESTED_OUTPUT AS
    FUNCTION fn_nested_output_line_rule(p_root IN JSON_OBJECT_T, p_o IN JSON_OBJECT_T, p_l IN JSON_OBJECT_T, p_j IN NUMBER, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_line_rule__dc JSON_OBJECT_T;
    BEGIN
        p_omitted := FALSE;
        v_line_rule__dc := JSON_OBJECT_T();
        v_line_rule__dc.put('Pos', p_j);
        v_line_rule__dc.put('LineId', p_l.get_String('id'));
        v_line_rule__dc.put('Price', p_l.get_Number('price'));
        RETURN v_line_rule__dc;
    END fn_nested_output_line_rule;

    FUNCTION fn_nested_output_tax_rule(p_root IN JSON_OBJECT_T, p_o IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_tax_rule__dc JSON_OBJECT_T;
    BEGIN
        p_omitted := FALSE;
        IF (p_o.get_String('taxRate') IS NOT NULL) THEN
            v_tax_rule__dc := JSON_OBJECT_T();
            v_tax_rule__dc.put('Rate', p_o.get_Number('taxRate'));
            RETURN v_tax_rule__dc;
        ELSE
            p_omitted := TRUE;
            RETURN NULL;
        END IF;
    END fn_nested_output_tax_rule;

    FUNCTION fn_nested_output_order_rule(p_root IN JSON_OBJECT_T, p_o IN JSON_OBJECT_T, p__errors IN OUT NOCOPY JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN JSON_OBJECT_T IS
        v_order_rule_lines JSON_ARRAY_T;
        v_forarr_0 JSON_ARRAY_T;
        v_order_rule_l JSON_OBJECT_T;
        v_order_rule_cnt0 NUMBER;
        v_order_rule_j NUMBER;
        v_order_rule__rc1 JSON_OBJECT_T;
        v_order_rule__ro1 BOOLEAN;
        v_order_rule__dc JSON_OBJECT_T;
        v_order_rule__rc2 JSON_OBJECT_T;
        v_order_rule__ro2 BOOLEAN;
    BEGIN
        p_omitted := FALSE;
        v_order_rule_lines := JSON_ARRAY_T();
        v_forarr_0 := TREAT(p_o.get_Array('lines').clone AS JSON_ARRAY_T);
        DECLARE
            v_sortj_0 PLS_INTEGER;
            v_sorttmp_0 JSON_ELEMENT_T;
            v_sorttmpkey_0 JSON_ELEMENT_T;
        BEGIN
            FOR v_sortk_0 IN 1 .. v_forarr_0.get_size - 1 LOOP
                v_sorttmp_0 := v_forarr_0.get(v_sortk_0);
                v_sorttmpkey_0 := TREAT(v_sorttmp_0 AS JSON_OBJECT_T).get('price');
                v_sortj_0 := v_sortk_0 - 1;
                WHILE v_sortj_0 >= 0 AND TREAT(v_forarr_0.get(v_sortj_0) AS JSON_OBJECT_T).get('price').compare_to(v_sorttmpkey_0) > 0 LOOP
                    v_forarr_0.put(v_sortj_0 + 1, v_forarr_0.get(v_sortj_0), TRUE);
                    v_sortj_0 := v_sortj_0 - 1;
                END LOOP;
                v_forarr_0.put(v_sortj_0 + 1, v_sorttmp_0, TRUE);
            END LOOP;
        END;
        v_order_rule_cnt0 := 1;
        FOR v_i_0 IN 0 .. v_forarr_0.get_size - 1 LOOP
            v_order_rule_l := TREAT(v_forarr_0.get(v_i_0) AS JSON_OBJECT_T);
            IF (v_order_rule_l.get_Boolean('active') = TRUE) THEN
                v_order_rule_j := v_order_rule_cnt0;
                v_order_rule_cnt0 := v_order_rule_cnt0 + 1;
                BEGIN
                    v_order_rule__rc1 := fn_nested_output_line_rule(p_root, p_o, v_order_rule_l, v_order_rule_j, v_order_rule__ro1);
                EXCEPTION
                    WHEN OTHERS THEN
                        IF NOT p__errors.has('line_rule') THEN
                            p__errors.put('line_rule', SQLERRM);
                        END IF;
                        v_order_rule__ro1 := TRUE;
                END;
                IF NOT v_order_rule__ro1 THEN
                    v_order_rule_lines.append(v_order_rule__rc1);
                END IF;
            END IF;
        END LOOP;
        v_order_rule__dc := JSON_OBJECT_T();
        v_order_rule__dc.put('OrderId', p_o.get_String('id'));
        BEGIN
            v_order_rule__rc2 := fn_nested_output_tax_rule(p_root, p_o, v_order_rule__ro2);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT p__errors.has('tax_rule') THEN
                    p__errors.put('tax_rule', SQLERRM);
                END IF;
                v_order_rule__ro2 := TRUE;
        END;
        IF NOT v_order_rule__ro2 THEN
            v_order_rule__dc.put('Tax', v_order_rule__rc2);
        END IF;
        v_order_rule__dc.put('Lines', v_order_rule_lines);
        RETURN v_order_rule__dc;
    END fn_nested_output_order_rule;

    PROCEDURE map_nested_output (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
        v_arr_Orders JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_forarr_1 JSON_ARRAY_T := v_srcroot.get_Array('orders');
        BEGIN
            FOR v_i_1 IN 0 .. v_forarr_1.get_size - 1 LOOP
                DECLARE
                    v_o JSON_OBJECT_T := TREAT(v_forarr_1.get(v_i_1) AS JSON_OBJECT_T);
                BEGIN
                    DECLARE
                        v_result_order_rule JSON_OBJECT_T;
                        v_omitted_order_rule BOOLEAN;
                    BEGIN
                        v_result_order_rule := fn_nested_output_order_rule(v_srcroot, v_o, v_rule_errors, v_omitted_order_rule);
                        IF NOT v_omitted_order_rule THEN
                            v_arr_Orders.append(v_result_order_rule);
                        END IF;
                    EXCEPTION
                        WHEN OTHERS THEN
                            IF NOT v_errors.EXISTS('order_rule') THEN
                                v_errors('order_rule') := SQLERRM;
                            END IF;
                    END;
                END;
            END LOOP;
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
                v_payload.put('mapping', 'nested_output');
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
                v_payload.put('mapping', 'nested_output');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        v_out_obj.put('Orders', v_arr_Orders);
        p_out := v_out_obj.TO_CLOB();
    END map_nested_output;

    PROCEDURE map_nested_output_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
        v_rule_errors JSON_OBJECT_T := JSON_OBJECT_T();
        v_arr_Orders JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
        DECLARE
            v_forarr_1 JSON_ARRAY_T := v_srcroot.get_Array('orders');
        BEGIN
            FOR v_i_1 IN 0 .. v_forarr_1.get_size - 1 LOOP
                DECLARE
                    v_o JSON_OBJECT_T := TREAT(v_forarr_1.get(v_i_1) AS JSON_OBJECT_T);
                BEGIN
                    DECLARE
                        v_result_order_rule JSON_OBJECT_T;
                        v_omitted_order_rule BOOLEAN;
                    BEGIN
                        v_result_order_rule := fn_nested_output_order_rule(v_srcroot, v_o, v_rule_errors, v_omitted_order_rule);
                        IF NOT v_omitted_order_rule THEN
                            v_arr_Orders.append(v_result_order_rule);
                        END IF;
                    EXCEPTION
                        WHEN OTHERS THEN
                            IF NOT v_errors.EXISTS('order_rule') THEN
                                v_errors('order_rule') := SQLERRM;
                            END IF;
                    END;
                END;
            END LOOP;
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
        v_out_obj.put('Orders', v_arr_Orders);
        p_out := v_out_obj.TO_CLOB();
    END map_nested_output_safe;
END NESTED_OUTPUT;
/
