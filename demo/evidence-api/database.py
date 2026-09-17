import psycopg


def find_course(connection: psycopg.Connection, course_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, title FROM courses WHERE id = %s",
            (course_id,),
        )
        return cursor.fetchone()

