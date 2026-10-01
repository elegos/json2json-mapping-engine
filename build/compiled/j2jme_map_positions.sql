CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_POSITIONS AS
    PROCEDURE map_positions (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_positions_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_POSITIONS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_POSITIONS AS
    FUNCTION fn_positions_first(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN p_root.get_Object('tx').get_Array('list').get_Object(0).get_String('id');
    END fn_positions_first;

    FUNCTION fn_positions_second_qty(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN NUMBER IS
    BEGIN
        p_omitted := FALSE;
        RETURN p_root.get_Object('tx').get_Array('list').get_Object(1).get_Number('qty');
    END fn_positions_second_qty;

    FUNCTION fn_positions_last_tag(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN p_root.get_Object('tx').get_Array('tags').get_String(2);
    END fn_positions_last_tag;

    FUNCTION fn_positions_flagged(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN (CASE WHEN MAPPING_OWNER.J2JME_FUNCTIONS.truthy(p_root.get_Object('tx').get_Array('list').get_Object(0).get('flag')) THEN 'T' ELSE 'F' END);
    END fn_positions_flagged;

    PROCEDURE map_positions (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        DECLARE
            v_result_first VARCHAR2(4000 CHAR);
            v_omitted_first BOOLEAN;
        BEGIN
            v_result_first := fn_positions_first(v_srcroot, v_omitted_first);
            IF NOT v_omitted_first THEN
                v_out_obj.put('First', v_result_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first') THEN
                    v_errors('first') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_second_qty NUMBER;
            v_omitted_second_qty BOOLEAN;
        BEGIN
            v_result_second_qty := fn_positions_second_qty(v_srcroot, v_omitted_second_qty);
            IF NOT v_omitted_second_qty THEN
                v_out_obj.put('SecondQty', v_result_second_qty);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('second_qty') THEN
                    v_errors('second_qty') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_last_tag VARCHAR2(4000 CHAR);
            v_omitted_last_tag BOOLEAN;
        BEGIN
            v_result_last_tag := fn_positions_last_tag(v_srcroot, v_omitted_last_tag);
            IF NOT v_omitted_last_tag THEN
                v_out_obj.put('LastTag', v_result_last_tag);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('last_tag') THEN
                    v_errors('last_tag') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_flagged VARCHAR2(4000 CHAR);
            v_omitted_flagged BOOLEAN;
        BEGIN
            v_result_flagged := fn_positions_flagged(v_srcroot, v_omitted_flagged);
            IF NOT v_omitted_flagged THEN
                v_out_obj.put('Flagged', v_result_flagged);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('flagged') THEN
                    v_errors('flagged') := SQLERRM;
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
                v_payload.put('mapping', 'positions');
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
                v_payload.put('mapping', 'positions');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_positions;

    PROCEDURE map_positions_safe (
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
            v_result_first VARCHAR2(4000 CHAR);
            v_omitted_first BOOLEAN;
        BEGIN
            v_result_first := fn_positions_first(v_srcroot, v_omitted_first);
            IF NOT v_omitted_first THEN
                v_out_obj.put('First', v_result_first);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('first') THEN
                    v_errors('first') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_second_qty NUMBER;
            v_omitted_second_qty BOOLEAN;
        BEGIN
            v_result_second_qty := fn_positions_second_qty(v_srcroot, v_omitted_second_qty);
            IF NOT v_omitted_second_qty THEN
                v_out_obj.put('SecondQty', v_result_second_qty);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('second_qty') THEN
                    v_errors('second_qty') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_last_tag VARCHAR2(4000 CHAR);
            v_omitted_last_tag BOOLEAN;
        BEGIN
            v_result_last_tag := fn_positions_last_tag(v_srcroot, v_omitted_last_tag);
            IF NOT v_omitted_last_tag THEN
                v_out_obj.put('LastTag', v_result_last_tag);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('last_tag') THEN
                    v_errors('last_tag') := SQLERRM;
                END IF;
        END;
        DECLARE
            v_result_flagged VARCHAR2(4000 CHAR);
            v_omitted_flagged BOOLEAN;
        BEGIN
            v_result_flagged := fn_positions_flagged(v_srcroot, v_omitted_flagged);
            IF NOT v_omitted_flagged THEN
                v_out_obj.put('Flagged', v_result_flagged);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                IF NOT v_errors.EXISTS('flagged') THEN
                    v_errors('flagged') := SQLERRM;
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
    END map_positions_safe;
END J2JME_MAP_POSITIONS;
/
