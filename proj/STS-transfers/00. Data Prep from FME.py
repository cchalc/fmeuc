# Databricks notebook source
# MAGIC %md ## We First Prep the data and download it

# COMMAND ----------

import mosaic as mos
from pyspark.sql.functions import *
from pyspark.sql import DataFrame, Row
from delta.tables import *
import random
import string

spark.conf.set("spark.databricks.labs.mosaic.geometry.api", "ESRI")
spark.conf.set("spark.databricks.labs.mosaic.index.system", "H3")
mos.enable_mosaic(spark, dbutils)

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE DATABASE IF NOT EXISTS ship2ship

# COMMAND ----------

# MAGIC %md ##AIS Data

# COMMAND ----------

# Create a unique database sufix to reuse this notebook
suffix_db = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
proj = "ship2ship"
dbutils.fs.mkdirs(f"/tmp/{proj}")
# Create checkpoints
checkpoints_dir = f"/tmp/{proj}/checkpoints_{suffix_db}"
dbutils.fs.rm(checkpoints_dir, True)
dbutils.fs.mkdirs(checkpoints_dir)

# COMMAND ----------

schema = """
  MMSI int, 
  BaseDateTime timestamp, 
  LAT double, 
  LON double, 
  SOG double, 
  COG double, 
  Heading double, 
  VesselName string, 
  IMO string, 
  CallSign string, 
  VesselType int, 
  Status int, 
  Length int, 
  Width int, 
  Draft double, 
  Cargo int, 
  TranscieverClass string
"""

# COMMAND ----------

# Read with Auto Loader
def autoload_to_table(data_source, source_format, table_name, checkpoint_directory):
    query = (spark.readStream
             .format("cloudFiles")
             .option("cloudFiles.format", source_format)
             .option("cloudFiles.schemaLocation", checkpoint_directory)
             .schema(schema)
             .load(data_source)
             .writeStream
             .option("checkpointLocation", checkpoint_directory)
             .option("mergeSchema", "true")
             .outputMode("append")
             .trigger(once=True)
             .table(table_name)
            )
    return query

# COMMAND ----------

query = autoload_to_table(data_source = f"/mnt/dev",
                          source_format = "csv",
                          table_name = "AIS",
                          checkpoint_directory = checkpoints_dir,
                         )

# COMMAND ----------

# FME job needs to be run in order to generate CSV
# make sure that the ../resources/storage.py is run before to mount storage
ais_path = "/mnt/dev/ais_raw.csv"

AIS_df = (
    spark.read.csv(ais_path, header=True, schema=schema)
)
display(AIS_df)

# COMMAND ----------

# (AIS_df.write.format("delta").mode("overwrite").saveAsTable("ship2ship.AIS"))

# COMMAND ----------

ais_from_table_df = (
    spark.read.table("ship2ship.ais")
)
display(ais_from_table_df)

# COMMAND ----------

# MAGIC %md ## Harbours
# MAGIC 
# MAGIC This data can be obtained from [here](https://data-usdot.opendata.arcgis.com/datasets/usdot::ports-major/about), and loaded accordingly.
# MAGIC 
# MAGIC We are choosing a buffer of `10 km` around harbours to arbitrarily define an area wherein we do not expect ship-to-ship transfers to take place.
# MAGIC Since our projection is not in metres, we convert from decimal degrees. With `(0.00001 - 0.000001)` as being equal to one metres at the equator
# MAGIC Ref: http://wiki.gis.com/wiki/index.php/Decimal_degrees

# COMMAND ----------

# MAGIC %sh
# MAGIC # we download data to dbfs:// mountpoint (/dbfs)
# MAGIC cd /dbfs/tmp/ship2ship/
# MAGIC wget -np -r -nH -L -q --cut-dirs=7 -O harbours.geojson "https://geo.dot.gov/mapping/rest/services/NTAD/Ports_Major/MapServer/0/query?outFields=*&where=1%3D1&f=geojson"

# COMMAND ----------

one_metre = 0.00001 - 0.000001
buffer = 10 * 1000 * one_metre

major_ports = (
    spark.read.format("json")
    .option("multiline", "true")
    .load("/tmp/ship2ship/harbours.geojson")
    .select("type", explode(col("features")).alias("feature"))
    .select(
        "type",
        col("feature.properties").alias("properties"),
        to_json(col("feature.geometry")).alias("json_geometry"),
    )
    .withColumn("geom", mos.st_aswkt(mos.st_geomfromgeojson("json_geometry")))
    .select(col("properties.PORT_NAME").alias("name"), "geom")
    .withColumn("geom", mos.st_buffer("geom", lit(buffer)))
)
display(major_ports)

# COMMAND ----------

# MAGIC %%mosaic_kepler
# MAGIC major_ports "geom" "geometry"

# COMMAND ----------

(
    major_ports.select("name", mos.mosaic_explode("geom", lit(9)).alias("mos"))
    .select("name", col("mos.index_id").alias("h3"))
    .write.mode("overwrite")
    .format("delta")
    .saveAsTable("ship2ship.harbours_h3")
)

# COMMAND ----------

harbours_h3 = spark.read.table("ship2ship.harbours_h3")
display(harbours_h3)

# COMMAND ----------

# MAGIC %%mosaic_kepler
# MAGIC "harbours_h3" "h3" "h3" 5_000

# COMMAND ----------


