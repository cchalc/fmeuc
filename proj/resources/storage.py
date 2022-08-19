# Databricks notebook source
# need to set up secret scope before
# https://docs.microsoft.com/en-us/azure/databricks/security/secrets/secret-scopes#create-an-azure-key-vault-backed-secret-scope-using-the-ui

BLOB_CONTAINER = 'dev'
BLOB_ACCOUNT = 'dltpe2np3vblob'
ACCOUNT_KEY = dbutils.secrets.get(scope='fmeuc_scope', key='storage-account-access-key')

# COMMAND ----------

# dbutils.fs.unmount("/mnt/bronze")

# COMMAND ----------

DIRECTORY = "/"

for layer in ["bronze", "silver", "gold"]:
  MOUNT_PATH = f"/mnt/{layer}"

  try:
    dbutils.fs.mount(
      source = f"wasbs://{BLOB_CONTAINER}@{BLOB_ACCOUNT}.blob.core.windows.net",
      mount_point = MOUNT_PATH,
      extra_configs = {
        f"fs.azure.account.key.{BLOB_ACCOUNT}.blob.core.windows.net":ACCOUNT_KEY
      }
    )
  except Exception as e:
    print(f"Already mounted on {MOUNT_PATH}. Unmount first if needed")

# COMMAND ----------

# MAGIC %fs ls /mnt/bronze
