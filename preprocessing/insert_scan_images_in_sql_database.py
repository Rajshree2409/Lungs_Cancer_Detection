import sys,os
import numpy as np
import dicom
import pyodbc
import pickle
import glob
import pandas as pd
from lung_cancer.connection_settings import get_connection_string, TABLE_SCAN_IMAGES
from config_preprocessing import STAGE1_LABELS, STAGE1_FOLDER


def create_table_scan_images(table_name, cursor, connector, drop_table=False):
    query = ""
    if drop_table:
        query += "IF OBJECT_ID(\'" + table_name + "\') IS NOT NULL DROP TABLE " + table_name + " "
    query += "CREATE TABLE " + table_name
    query += """ ( 
    patient_id varchar(50) not null, 
    number_images integer not null, 
    image_rows integer not null, 
    image_cols integer not null,
    array varbinary(max) not null 
    )
    """ 
    cursor.execute(query)
    connector.commit()


def get_3d_data(path):
    slices = [dicom.read_file(os.path.join(path, s)) for s in os.listdir(path)]
    slices.sort(key=lambda x: int(x.InstanceNumber))
    return np.stack([s.pixel_array for s in slices])


def get_image_batch(path):
    sample_image = get_3d_data(path)
    sample_image[sample_image == -2000] = 0
    batch = []
    for i in range(sample_image.shape[0]):
        img = sample_image[i]
        img = 255.0 / np.amax(img) * img
        batch.append(img)
    
    batch = np.array(batch, dtype='int')
    return batch


def generate_insert_query(table_name):
    query = "INSERT INTO " + table_name + "( patient_id, number_images, image_rows, image_cols, array ) VALUES (?,?,?,?,?)"
    return query


if __name__ == "__main__":

    #Create SQL database connection and table
    connection_string = get_connection_string()
    conn = pyodbc.connect(connection_string)
    cur = conn.cursor()
    print("Creating table {}".format(TABLE_SCAN_IMAGES))
    create_table_scan_images(TABLE_SCAN_IMAGES, cur, conn, True)

    #Insert all patient images
    df = pd.read_csv(STAGE1_LABELS)
    print("Inserting {} patient images in the database".format(df.shape[0]))
    q_insert = generate_insert_query(TABLE_SCAN_IMAGES)
    for i, patient_id in enumerate(df['id'].tolist()):
        folder = os.path.join(STAGE1_FOLDER, patient_id)
        print("Inserting patient #{} with id: {}".format(i, patient_id))
        batch = get_image_batch(folder)
        batch_serial = pickle.dumps(batch, protocol=0)
        cur.execute(q_insert, patient_id, batch.shape[0], batch.shape[1], batch.shape[2], batch_serial)
        conn.commit()

    print("Images inserted")
    conn.close()
