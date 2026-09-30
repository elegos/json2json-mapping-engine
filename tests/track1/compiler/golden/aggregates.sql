CREATE OR REPLACE PACKAGE AGGREGATES AS
    PROCEDURE map_aggregates (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_aggregates_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END AGGREGATES;
/

CREATE OR REPLACE PACKAGE BODY AGGREGATES AS
    FUNCTION fn_aggregates_max_price(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_max_price__agg NUMBER;
        v_aggarr_0 JSON_ARRAY_T;
        v_aggacc_0 JSON_ELEMENT_T;
        v_aggcur_0 JSON_ELEMENT_T;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_0 := p_root.get_Array('items');
        v_aggacc_0 := NULL;
        FOR v_aggk_0 IN 0 .. v_aggarr_0.get_size - 1 LOOP
            v_aggcur_0 := TREAT(v_aggarr_0.get(v_aggk_0) AS JSON_OBJECT_T).get('price');
            IF v_aggacc_0 IS NULL OR v_aggcur_0.compare_to(v_aggacc_0) > 0 THEN
                v_aggacc_0 := v_aggcur_0;
            END IF;
        END LOOP;
        v_max_price__agg := v_aggacc_0.to_number();
        RETURN v_max_price__agg;
    END fn_aggregates_max_price;

    FUNCTION fn_aggregates_total_price(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
        v_total_price__agg NUMBER;
        v_aggarr_1 JSON_ARRAY_T;
        v_aggacc_1 NUMBER;
    BEGIN
        p_omitted := FALSE;
        v_aggarr_1 := p_root.get_Array('items');
        v_aggacc_1 := 0;
        FOR v_aggk_1 IN 0 .. v_aggarr_1.get_size - 1 LOOP
            v_aggacc_1 := v_aggacc_1 + TREAT(v_aggarr_1.get(v_aggk_1) AS JSON_OBJECT_T).get_Number('price');
        END LOOP;
        v_total_price__agg := v_aggacc_1;
        RETURN v_total_price__agg;
    END fn_aggregates_total_price;

    PROCEDURE map_aggregates (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_max_price NUMBER;
            v_omitted_max_price BOOLEAN;
        BEGIN
            v_result_max_price := fn_aggregates_max_price(v_srcroot, v_omitted_max_price);
            IF NOT v_omitted_max_price THEN
                v_out_obj.put('MaxPrice', v_result_max_price);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('max_price') THEN
                    v_errors('max_price') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_total_price NUMBER;
            v_omitted_total_price BOOLEAN;
        BEGIN
            v_result_total_price := fn_aggregates_total_price(v_srcroot, v_omitted_total_price);
            IF NOT v_omitted_total_price THEN
                v_out_obj.put('TotalPrice', v_result_total_price);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('total_price') THEN
                    v_errors('total_price') := SQLERRM;
                END IF;
        END;
        BEGIN
            v_out_obj.put('ItemCount', v_srcroot.get_Array('items').get_size);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ItemCount') THEN
                    v_errors('ItemCount') := SQLERRM;
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
                v_payload.put('mapping', 'aggregates');
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
                v_payload.put('mapping', 'aggregates');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_aggregates;

    PROCEDURE map_aggregates_safe (
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
            v_result_max_price NUMBER;
            v_omitted_max_price BOOLEAN;
        BEGIN
            v_result_max_price := fn_aggregates_max_price(v_srcroot, v_omitted_max_price);
            IF NOT v_omitted_max_price THEN
                v_out_obj.put('MaxPrice', v_result_max_price);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('max_price') THEN
                    v_errors('max_price') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_total_price NUMBER;
            v_omitted_total_price BOOLEAN;
        BEGIN
            v_result_total_price := fn_aggregates_total_price(v_srcroot, v_omitted_total_price);
            IF NOT v_omitted_total_price THEN
                v_out_obj.put('TotalPrice', v_result_total_price);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('total_price') THEN
                    v_errors('total_price') := SQLERRM;
                END IF;
        END;
        BEGIN
            v_out_obj.put('ItemCount', v_srcroot.get_Array('items').get_size);
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('ItemCount') THEN
                    v_errors('ItemCount') := SQLERRM;
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
    END map_aggregates_safe;
END AGGREGATES;
/
