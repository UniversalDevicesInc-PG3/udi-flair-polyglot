#!/usr/bin/env python3

"""
This is a NodeServer for Flair Vent Sys/tem written by automationgeek (Jean-Francois Tremblay) 
based on the NodeServer template for Polyglot v2 written in Python2/3 by Einstein.42 (James Milne) milne.james@gmail.com
Using the Flair API Client - https://github.com/flair-systems/flair-api-client-py
"""

import udi_interface
import hashlib
import time
import json
import sys
from copy import deepcopy
from threading import Thread
from flair_api import make_client
from flair_api import ApiError
from flair_api import EmptyBodyException

LOGGER = udi_interface.LOGGER
SERVERDATA = json.load(open('server.json'))
VERSION = SERVERDATA['credits'][0]['version']

def get_profile_info(logger):
    pvf = 'profile/version.txt'
    try:
        with open(pvf) as f:
            pv = f.read().replace('\n', '')
    except Exception as err:
        logger.error('get_profile_info: failed to read  file {0}: {1}'.format(pvf,err), exc_info=True)
        pv = 0
    f.close()
    return { 'version': pv }

class Controller(udi_interface.Node):

    def __init__(self, polyglot, primary, address, name):
        super(Controller, self).__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.name = 'Flair'
        self.queryON = False
        self.client_id = ""
        self.client_secret = ""
        self.api_client = None
        self.discovery_thread = None
        self.hb = 0

        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)

        polyglot.ready()
        polyglot.addNode(self)

    def parameterHandler(self, params):
        self.poly.Notices.clear()
        try:
            if 'client_id' in params:
                self.client_id = params['client_id']

            if 'client_secret' in params:
                self.client_secret = params['client_secret']

            if self.client_id == "" or self.client_secret == "" :
                LOGGER.error('Flair requires \'client_id\' \'client_secret\' parameters to be specified in custom configuration.')
                self.poly.Notices['cfg'] = 'Flair requires you specify both the client_id and client_secret custom parameters'
                return False
            else:
                self.heartbeat()
                self.discover()
                
        except Exception as ex:
            LOGGER.error('Error starting Flair NodeServer: %s', str(ex))


    def start(self):
        self.poly.updateProfile()
        self.poly.setCustomParamsDoc()

        LOGGER.info('Started Flair for v3 NodeServer version %s', str(VERSION))
        self.setDriver('ST', 0)

            
    def poll(self, pollflag):
        if 'shortPoll' in pollflag:
            try:
                if self.discovery_thread is not None:
                    if self.discovery_thread.is_alive():
                        LOGGER.debug('Skipping shortPoll() while discovery in progress...')
                        return
                    else:
                        self.discovery_thread = None
                self.update()
            except Exception as ex:
                LOGGER.error('Error shortPoll: %s', str(ex))
        else:
            try :
                self.heartbeat()
                if self.discovery_thread is not None:
                    if self.discovery_thread.is_alive():
                        LOGGER.debug('Skipping longPoll() while discovery in progress...')
                        return	
                    else: 
                        self.discovery_thread = None	
                    
                # Renew Token
                self.api_client.oauth_token()
                self.api_client.api_root_response()
            except Exception as ex:
                LOGGER.error('Error longPoll: %s', str(ex))
    
    def heartbeat(self):
        LOGGER.debug('heartbeat hb={}'.format(str(self.hb)))
        if self.hb == 0:
            self.reportCmd("DON",2)
            self.hb = 1
        else:
            self.reportCmd("DOF",2)
            self.hb = 0
            
    def query(self):
        for node in self.poly.nodes():
            node.reportDrivers()
            
    def update(self):
        try :
            self.setDriver('ST', 1)
            for node in self.poly.nodes():
                if node.queryON == True :
                    node.update()
        except Exception as ex:
            LOGGER.error('Error update: %s', str(ex))
    
    def runDiscover(self,command):
        self.discover()
    
    def discover(self, *args, **kwargs):  
        if self.discovery_thread is not None:
            if self.discovery_thread.is_alive():
                LOGGER.info('Discovery is still in progress')
                return
        self.discovery_thread = Thread(target=self._discovery_process)
        self.discovery_thread.start()

    def _discovery_process(self):
        
        try:
            self.api_client = make_client(self.client_id,self.client_secret,'https://api.flair.co/')
            structures = self.api_client.get('structures')
        except ApiError as ex:
            LOGGER.error('Error _discovery_process: %s', str(ex))
            
        for structure in structures:
            strHash = str(int(hashlib.md5(structure.attributes['name'].encode('utf8')).hexdigest(), 16) % (10 ** 8))
            self.poly.addNode(FlairStructure(self.poly, strHash, strHash,structure.attributes['name'],structure))
            #time.sleep(5)
            rooms = structure.get_rel('rooms')
            roomNumber = 1
            for room in rooms:
                strHashRoom = str(int(hashlib.md5(room.attributes['name'].encode('utf8')).hexdigest(), 16) % (10 ** 8))
                self.poly.addNode(FlairRoom(self.poly, strHash,strHashRoom,'R' + str(roomNumber) + '_' + room.attributes['name'],room))
                
                try:
                    pucks = room.get_rel('pucks')
                    for puck in pucks:
                        strHashPucks = str(int(hashlib.md5(puck.attributes['name'].encode('utf8')).hexdigest(), 16) % (10 ** 8))
                        self.poly.addNode(FlairPuck(self.poly, strHash,strHashRoom[:4]+strHashPucks,'R' + str(roomNumber) + '_' + puck.attributes['name'],puck,room))
                except EmptyBodyException as ex:
                    pass
            
                try:
                    vents = room.get_rel('vents')
                    for vent in vents :
                        strHashVents = str(int(hashlib.md5(vent.attributes['name'].encode('utf8')).hexdigest(), 16) % (10 ** 8))
                        self.poly.addNode(FlairVent(self.poly, strHash, strHashRoom[:4]+strHashVents ,'R' + str(roomNumber) + '_' + vent.attributes['name'],vent,room))
                except EmptyBodyException as ex:
                    pass
                
                roomNumber = roomNumber + 1
                           
    def delete(self):
        LOGGER.info('Deleting Flair')
        
    id = 'controller'
    commands = {    'QUERY': query,        
                    'DISCOVERY' : runDiscover
               }
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 2}]
    
class FlairStructure(udi_interface.Node):

    SPM = ['Home Evenness For Active Rooms Flair Setpoint','Home Evenness For Active Rooms Follow Third Party']
    HAM = ['Manual','Third Party Home Away','Flair Autohome Autoaway']
    MODE = ['manual','auto']
    
    def __init__(self, controller, primary, address, name, struct):

        super(FlairStructure, self).__init__(controller, primary, address, name)
        self.queryON = True
        self.name = name
        self.objStructure = struct
   
    def setMode(self, command):
        try :
            self.objStructure.update(attributes={'mode': self.MODE[int(command.get('value'))]})  
            self.setDriver('GV4', self.MODE.index(self.objStructure.attributes['mode']))
        except ApiError as ex:
            LOGGER.error('Error setMode: %s', str(ex))
       
    def setAway(self, command):
        try:
            self.objStructure.update(attributes={'home-away-mode': self.HAM[int(command.get('value'))]})
            self.setDriver('GV5', self.HAM.index(self.objStructure.attributes['home-away-mode']))
        except ApiError as ex:
            LOGGER.error('Error setAway: %s', str(ex))
    
    def setEven(self, command):
        try:    
            self.objStructure.update(attributes={'set-point-mode': self.SPM[int(command.get('value'))]})
            self.setDriver('GV6', self.SPM.index(self.objStructure.attributes['set-point-mode']))
        except ApiError as ex:
            LOGGER.error('Error setEven: %s', str(ex))
    
    def query(self):
        self.reportDrivers()
        
    def update(self):
        try:
            if  self.objStructure.attributes['is-active'] is True:
                self.setDriver('GV2', 1)
            else:
                self.setDriver('GV2', 0)
            
            tempC = int(self.objStructure.attributes['set-point-temperature-c'])
            tempF = (tempC * 9/5) + 32
            
            self.setDriver('CLITEMP', round(tempC,1))
            self.setDriver('GV7', round(tempF,1))

            if  self.objStructure.attributes['home'] is True:
                self.setDriver('GV3', 1)
            else:
                self.setDriver('GV3', 0)

            self.setDriver('GV6', self.SPM.index(self.objStructure.attributes['set-point-mode']))
            self.setDriver('GV5', self.HAM.index(self.objStructure.attributes['home-away-mode']))
            self.setDriver('GV4', self.MODE.index(self.objStructure.attributes['mode']))
            
        except ApiError as ex:
            LOGGER.error('Error query: %s', str(ex))
            
    drivers = [{'driver': 'GV2', 'value': 0, 'uom': 2},
                {'driver': 'CLITEMP', 'value': 0, 'uom': 4},
                {'driver': 'GV3', 'value': 0, 'uom': 2},
                {'driver': 'GV4', 'value': 0, 'uom': 25},
                {'driver': 'GV5', 'value': 0, 'uom': 25},
                {'driver': 'GV6', 'value': 0, 'uom': 25},
                {'driver': 'GV7', 'value': 0, 'uom': 17} ]
    
    id = 'FLAIR_STRUCT'
    commands = {'SET_MODE' : setMode, 
                'SET_AWAY' : setAway, 
                'SET_EVENESS' : setEven,
                'QUERY': query }
   
class FlairVent(udi_interface.Node):

    def __init__(self, controller, primary, address, name, vent,room):

        super(FlairVent, self).__init__(controller, primary, address, name)
        self.queryON = True
        self.name = name
        self.objVent = vent
        self.objRoom = room
        
    def setOpen(self, command):
        
        try:
            self.objVent.update(attributes={'percent-open': int(command.get('value'))})
            self.setDriver('GV1', self.objVent.attributes['percent-open'])
        except ApiError as ex:
            LOGGER.error('Error setOpen: %s', str(ex))

    def query(self):
        self.reportDrivers()           
            
    def update(self):
        try:
            if  self.objVent.attributes['inactive'] is True:
                self.setDriver('GV2', 1)
            else:
                self.setDriver('GV2', 0)

            self.setDriver('GV1', self.objVent.attributes['percent-open'])
            self.setDriver('GV8', self.objVent.attributes['voltage'])
            
            # Get current-reading
            creading = self.objVent.get_rel('current-reading')
            self.setDriver('GV9', creading.attributes['duct-pressure'])
            
            tempC = int(creading.attributes['duct-temperature-c'])
            tempF = (tempC * 9/5) + 32
            
            self.setDriver('GV10', tempC)
            self.setDriver('GV11', tempF)
            self.setDriver('GV12', creading.attributes['rssi'])
        
        except ApiError as ex:
            LOGGER.error('Error query: %s', str(ex))
             
    drivers = [{'driver': 'GV2', 'value': 0, 'uom': 2},
              {'driver': 'GV1', 'value': 0, 'uom': 51},
              {'driver': 'GV8', 'value': 0, 'uom': 72},
              {'driver': 'GV9', 'value': 0, 'uom': 31},
              {'driver': 'GV10', 'value': 0, 'uom': 4},
              {'driver': 'GV11', 'value': 0, 'uom': 17},
              {'driver': 'GV12', 'value': 0, 'uom': 56}]
    
    id = 'FLAIR_VENT'
    commands = { 'SET_OPEN' : setOpen,
                 'QUERY': query}
    
class FlairPuck(udi_interface.Node):

    def __init__(self, controller, primary, address, name, puck,room):

        super(FlairPuck, self).__init__(controller, primary, address, name)
        self.queryON = True
        self.name = name
        self.objPuck = puck
        self.objRoom = room
        
    def query(self):
        self.reportDrivers()
    
    def update(self):
        try:
            if  self.objPuck.attributes['inactive'] is True:
                self.setDriver('GV2', 1)
            else:
                self.setDriver('GV2', 0)

            LOGGER.debug('puck attributes: {}'.format(self.objPuck.attributes))
            tempC = int(self.objPuck.attributes['current-temperature-c'])  if self.objPuck.attributes['current-temperature-c'] != None else 0 
            tempF = (tempC * 9/5) + 32
                
            self.setDriver('CLITEMP', round(tempC,1))
            self.setDriver('GV7', round(tempF,1))
            self.setDriver('CLIHUM', self.objPuck.attributes['current-humidity'])
            
            # Get current-reading
            creading = self.objPuck.get_rel('current-reading')
            LOGGER.debug('puck current-reading: {}'.format(creading))
            self.setDriver('GV12', creading.attributes['rssi'])
            self.setDriver('GV8', creading.attributes['system-voltage'])
               
        except ApiError as ex:
            LOGGER.error('Error query: %s', str(ex))  
            
    drivers = [ {'driver': 'GV2', 'value': 0, 'uom': 2},
                {'driver': 'CLITEMP', 'value': 0, 'uom': 4},
                {'driver': 'CLIHUM', 'value': 0, 'uom': 51},
                {'driver': 'GV7', 'value': 0, 'uom': 17},
                {'driver': 'GV8', 'value': 0, 'uom': 72},
                {'driver': 'GV12', 'value': 0, 'uom': 56}]
    
    id = 'FLAIR_PUCK'
    commands = {  'QUERY': query }

class FlairRoom(udi_interface.Node):

    def __init__(self, controller, primary, address, name,room):

        super(FlairRoom, self).__init__(controller, primary, address, name)
        self.queryON = True
        self.name = name
        self.objRoom = room
        
    def query(self):
        self.reportDrivers()
    
    def update(self):
        try:
            if self.objRoom.attributes['active'] is True:
                self.setDriver('GV2', 0)
            else:
                self.setDriver('GV2', 1)

            if self.objRoom.attributes['current-temperature-c'] is not None :
                
                tempC = int(self.objRoom.attributes['current-temperature-c']) if self.objRoom.attributes['current-temperature-c'] != None else 0 
                tempF = (tempC * 9/5) + 32
                
                self.setDriver('CLITEMP', round(tempC,1))
                self.setDriver('GV7',round(tempF,1))
            else:
                self.setDriver('CLITEMP',0)
                self.setDriver('GV7',0)
                
            if self.objRoom.attributes['current-humidity'] is None:
                self.setDriver('CLIHUM',0)
            else:
                self.setDriver('CLIHUM', self.objRoom.attributes['current-humidity'])

            if self.objRoom.attributes['set-point-c'] is not None:
                self.setDriver('CLISPC', round(self.objRoom.attributes['set-point-c'],1))
            else:
                self.setDriver('CLISPC', 0)
         
        except ApiError as ex:
            LOGGER.error('Error query: %s', str(ex))  
    
    def setTemp(self, command):
        try:
            self.objRoom.update(attributes={'set-point-c': command.get('value')})
            self.setDriver('CLISPC', round(self.objRoom.attributes['set-point-c'],1))

        except ApiError as ex:
            LOGGER.error('Error setTemp: %s', str(ex))

    drivers = [ {'driver': 'GV2', 'value': 0, 'uom': 2},
                {'driver': 'CLITEMP', 'value': 0, 'uom': 4},
                {'driver': 'CLIHUM', 'value': 0, 'uom': 51},
                {'driver': 'CLISPC', 'value': 0, 'uom': 4},
                {'driver': 'GV7', 'value': 0, 'uom': 17}]
    
    id = 'FLAIR_ROOM'
    commands = { 'QUERY': query, 
                 'SET_TEMP': setTemp }    
    
if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start('3.0.0')
        Controller(polyglot, 'controller', 'controller', 'FlairNodeServer')
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
