import sqlite3

from flask import Flask, jsonify, request

from config import STATIONS_5001A, STATIONS_5001B


app = Flask(__name__)

DB_PATH = "data/busflow.db"

STATION_NAMES = {
    station["id"]: station["name"]
    for station in STATIONS_5001A + STATIONS_5001B
}


def get_db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


@app.route("/")
def home():
    connection = get_db_connection()

    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM congestion
        """
    ).fetchone()[0]

    connection.close()

    return f"BusFlow 데이터 개수: {count}"


@app.route("/api/routes")
def get_routes():
    connection = get_db_connection()

    rows = connection.execute(
        """
        SELECT
            route_id,
            COUNT(*) AS data_count
        FROM congestion
        GROUP BY route_id
        ORDER BY route_id
        """
    ).fetchall()

    connection.close()

    routes = [
        {
            "route_id": row["route_id"],
            "data_count": row["data_count"],
        }
        for row in rows
    ]

    return jsonify(routes)


@app.route("/api/stations/<route_id>")
def get_stations(route_id):
    connection = get_db_connection()

    rows = connection.execute(
        """
        SELECT DISTINCT
            station_id,
            station_seq
        FROM congestion
        WHERE route_id = ?
        ORDER BY station_seq
        """,
        (route_id,),
    ).fetchall()

    connection.close()

    stations = [
        {
            "station_id": row["station_id"],
            "station_name": STATION_NAMES.get(
                row["station_id"],
                "알 수 없는 정류장",
            ),
            "station_seq": row["station_seq"],
        }
        for row in rows
    ]

    return jsonify(stations)


@app.route("/api/congestion/<route_id>/<station_id>")
def get_congestion(route_id, station_id):
    connection = get_db_connection()

    rows = connection.execute(
        """
        SELECT
            time_zone,
            ROUND(AVG(congestion), 1) AS avg_congestion,
            COUNT(*) AS data_count
        FROM congestion
        WHERE route_id = ?
          AND station_id = ?
        GROUP BY time_zone
        ORDER BY time_zone
        """,
        (route_id, station_id),
    ).fetchall()

    connection.close()

    congestion_data = [
        {
            "time_zone": row["time_zone"],
            "avg_congestion": row["avg_congestion"],
            "data_count": row["data_count"],
        }
        for row in rows
    ]

    return jsonify(congestion_data)


@app.route("/api/congestion/<route_id>/<station_id>/by-day")
def get_congestion_by_day(route_id, station_id):
    connection = get_db_connection()

    rows = connection.execute(
        """
        SELECT
            dow_nm,
            time_zone,
            ROUND(AVG(congestion), 1) AS avg_congestion,
            COUNT(*) AS data_count
        FROM congestion
        WHERE route_id = ?
          AND station_id = ?
        GROUP BY dow_nm, time_zone
        ORDER BY dow_nm, time_zone
        """,
        (route_id, station_id),
    ).fetchall()

    connection.close()

    congestion_data = [
        {
            "day": row["dow_nm"],
            "time_zone": row["time_zone"],
            "avg_congestion": row["avg_congestion"],
            "data_count": row["data_count"],
        }
        for row in rows
    ]

    return jsonify(congestion_data)


if __name__ == "__main__":
    app.run(debug=True)