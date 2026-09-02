import os
import sqlite3


DB_PATH = "data/weather.db"


def create_weather_table():

    os.makedirs(
        os.path.dirname(DB_PATH),
        exist_ok=True
    )

    conn = sqlite3.connect(
        DB_PATH
    )

    cursor = conn.cursor()


    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS weather (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            opr_ymd TEXT NOT NULL,

            route_id TEXT NOT NULL,

            station_id TEXT NOT NULL,

            station_seq INTEGER,

            time_zone TEXT NOT NULL,

            weather_station_id TEXT,

            weather_station_name TEXT,

            temperature REAL,

            rainfall REAL,

            humidity REAL,

            wind_speed REAL,

            snow_depth REAL,

            UNIQUE (
                opr_ymd,
                route_id,
                station_id,
                time_zone
            )
        )
        """
    )


    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_weather_join

        ON weather (
            opr_ymd,
            route_id,
            station_id,
            time_zone
        )
        """
    )


    conn.commit()

    conn.close()


def save_weather(items):

    conn = sqlite3.connect(
        DB_PATH
    )

    cursor = conn.cursor()


    for item in items:

        cursor.execute(
            """
            INSERT OR REPLACE INTO weather (

                opr_ymd,
                route_id,
                station_id,
                station_seq,
                time_zone,

                weather_station_id,
                weather_station_name,

                temperature,
                rainfall,
                humidity,
                wind_speed,
                snow_depth
            )

            VALUES (
                ?, ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?, ?, ?
            )
            """,

            (
                item["opr_ymd"],
                item["route_id"],
                item["station_id"],
                item["station_seq"],
                item["time_zone"],

                item["weather_station_id"],
                item["weather_station_name"],

                item["temperature"],
                item["rainfall"],
                item["humidity"],
                item["wind_speed"],
                item["snow_depth"],
            )
        )


    conn.commit()

    conn.close()


if __name__ == "__main__":

    create_weather_table()

    print("weather.db 생성 완료")
