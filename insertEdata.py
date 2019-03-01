#!/usr/bin/python

import os,sys               # to get path
from subprocess import call
import meter_db as mdb      # for sql queries


def uploadEdata(dataFileName):
    metaID = dataFileName.split('_')[0]
    sqlq = "LOAD DATA INFILE '/home/meter/data/" + dataFileName + "' INTO TABLE Electricity FIELDS TERMINATED BY ',' (dt,Watt) SET Meta_idMeta = " + str(metaID) + ";"
    mdb.executeSQL(sqlq)
    mdb.commit()
    updateDataQuality(metaID, 1)

    # update status
    sqlq = "UPDATE Household \
            SET `status`="6"\
            WHERE `idHousehold` ='" + str(householdID) + "';"
    mdb.executeSQL(sqlq)
    mdb.commit()

    # produce 1min and 10min data
    os.system('cd Analysis/scripts/ && python /home/meter/Analysis/scripts/el_downsample.py')



def updateDataQuality(idMeta, Quality):
    """ set Quality in Meta table """
    # XXX add for diaries
    sqlq = "UPDATE Meta \
            SET `Quality`= %s \
            WHERE `idMeta` = %s;" % (Quality, idMeta)
    mdb.executeSQL(sqlq)
    mdb.commit()

uploadEdata(sys.argv[1]) 
