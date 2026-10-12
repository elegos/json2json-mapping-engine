CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAP_GROUPS AS
    PROCEDURE map_groups (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_groups_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );
END J2JME_MAP_GROUPS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAP_GROUPS AS
    FUNCTION fn_groups_post_op(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN 'POST';
    END fn_groups_post_op;

    FUNCTION fn_groups_post_name(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_post_name__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_post_name__ret := UPPER(p_root.get_String('name'));
        IF v_post_name__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_post_name__ret;
    END fn_groups_post_name;

    FUNCTION fn_groups_delete_op(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
    BEGIN
        p_omitted := FALSE;
        RETURN 'DELETE';
    END fn_groups_delete_op;

    FUNCTION fn_groups_the_id(p_root IN JSON_OBJECT_T, p_omitted OUT BOOLEAN) RETURN VARCHAR2 IS
        v_the_id__ret VARCHAR2(4000 CHAR);
    BEGIN
        p_omitted := FALSE;
        v_the_id__ret := p_root.get_String('id');
        IF v_the_id__ret IS NULL THEN p_omitted := TRUE; END IF;
        RETURN v_the_id__ret;
    END fn_groups_the_id;

    PROCEDURE map_groups (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        IF (v_srcroot.get_String('operation') = 'POST') THEN
            DECLARE
                v_result_post_op VARCHAR2(4000 CHAR);
                v_omitted_post_op BOOLEAN;
            BEGIN
                v_result_post_op := fn_groups_post_op(v_srcroot, v_omitted_post_op);
                IF NOT v_omitted_post_op THEN
                    v_out_obj.put('operation', v_result_post_op);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('post_op') THEN
                        v_errors('post_op') := SQLERRM;
                    END IF;
            END;
            DECLARE
                v_result_the_id VARCHAR2(4000 CHAR);
                v_omitted_the_id BOOLEAN;
            BEGIN
                v_result_the_id := fn_groups_the_id(v_srcroot, v_omitted_the_id);
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
                v_result_post_name VARCHAR2(4000 CHAR);
                v_omitted_post_name BOOLEAN;
            BEGIN
                v_result_post_name := fn_groups_post_name(v_srcroot, v_omitted_post_name);
                IF NOT v_omitted_post_name THEN
                    v_out_obj.put('name', v_result_post_name);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('post_name') THEN
                        v_errors('post_name') := SQLERRM;
                    END IF;
            END;
        END IF;
        IF (v_srcroot.get_String('operation') = 'DELETE') THEN
            DECLARE
                v_result_delete_op VARCHAR2(4000 CHAR);
                v_omitted_delete_op BOOLEAN;
            BEGIN
                v_result_delete_op := fn_groups_delete_op(v_srcroot, v_omitted_delete_op);
                IF NOT v_omitted_delete_op THEN
                    v_out_obj.put('operation', v_result_delete_op);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('delete_op') THEN
                        v_errors('delete_op') := SQLERRM;
                    END IF;
            END;
            DECLARE
                v_result_the_id VARCHAR2(4000 CHAR);
                v_omitted_the_id BOOLEAN;
            BEGIN
                v_result_the_id := fn_groups_the_id(v_srcroot, v_omitted_the_id);
                IF NOT v_omitted_the_id THEN
                    v_out_obj.put('id', v_result_the_id);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('the_id') THEN
                        v_errors('the_id') := SQLERRM;
                    END IF;
            END;
        END IF;

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
                v_payload.put('mapping', 'groups');
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
                v_payload.put('mapping', 'groups');
                v_payload.put('total_errors', v_errors.COUNT);
                v_payload.put('shown', v_shown);
                v_payload.put('errors', v_err_arr);
                RAISE_APPLICATION_ERROR(-20000, v_payload.to_string());
            END;
        END IF;
        p_out := v_out_obj.TO_CLOB();
    END map_groups;

    PROCEDURE map_groups_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
        v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
        v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
        TYPE t_error_map IS TABLE OF VARCHAR2(4000) INDEX BY VARCHAR2(200);
        v_errors   t_error_map;
    BEGIN
        IF (v_srcroot.get_String('operation') = 'POST') THEN
            DECLARE
                v_result_post_op VARCHAR2(4000 CHAR);
                v_omitted_post_op BOOLEAN;
            BEGIN
                v_result_post_op := fn_groups_post_op(v_srcroot, v_omitted_post_op);
                IF NOT v_omitted_post_op THEN
                    v_out_obj.put('operation', v_result_post_op);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('post_op') THEN
                        v_errors('post_op') := SQLERRM;
                    END IF;
            END;
            DECLARE
                v_result_the_id VARCHAR2(4000 CHAR);
                v_omitted_the_id BOOLEAN;
            BEGIN
                v_result_the_id := fn_groups_the_id(v_srcroot, v_omitted_the_id);
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
                v_result_post_name VARCHAR2(4000 CHAR);
                v_omitted_post_name BOOLEAN;
            BEGIN
                v_result_post_name := fn_groups_post_name(v_srcroot, v_omitted_post_name);
                IF NOT v_omitted_post_name THEN
                    v_out_obj.put('name', v_result_post_name);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('post_name') THEN
                        v_errors('post_name') := SQLERRM;
                    END IF;
            END;
        END IF;
        IF (v_srcroot.get_String('operation') = 'DELETE') THEN
            DECLARE
                v_result_delete_op VARCHAR2(4000 CHAR);
                v_omitted_delete_op BOOLEAN;
            BEGIN
                v_result_delete_op := fn_groups_delete_op(v_srcroot, v_omitted_delete_op);
                IF NOT v_omitted_delete_op THEN
                    v_out_obj.put('operation', v_result_delete_op);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('delete_op') THEN
                        v_errors('delete_op') := SQLERRM;
                    END IF;
            END;
            DECLARE
                v_result_the_id VARCHAR2(4000 CHAR);
                v_omitted_the_id BOOLEAN;
            BEGIN
                v_result_the_id := fn_groups_the_id(v_srcroot, v_omitted_the_id);
                IF NOT v_omitted_the_id THEN
                    v_out_obj.put('id', v_result_the_id);
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    IF NOT v_errors.EXISTS('the_id') THEN
                        v_errors('the_id') := SQLERRM;
                    END IF;
            END;
        END IF;

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
    END map_groups_safe;
END J2JME_MAP_GROUPS;
/
