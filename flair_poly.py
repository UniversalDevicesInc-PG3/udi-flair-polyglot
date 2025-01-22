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
VERSION = '3.0.1'

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
        #polyglot.addNode(self)

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
        '''
        This appears to just send the data we got during discovery.  Nothing
        here is being updated.
        '''
        try:
            rooms = self.objStructure.get_rel('rooms')
            for room in rooms:
                '''
                Here's what we have for each room.  How do we map this to
                the room nodes?
                {
                'name': 'Guest Room',
                'created-at': '2024-06-29T01:38:25.448999+00:00',
                'set-point-c': 18.33,
                'pucks-inactive': 'Active',
                'room-type': None,
                'active': True, 
                'updated-at': '2025-01-21T23:00:18.335236+00:00', 
                'hold-until-schedule-event': True, 
                'humidity-away-max': 80, 
                'room-conclusion-mode': 'HEAT', 
                'windows': None, 
                'temp-away-min-c': 16.0, 
                'state-updated-at': '2025-01-21T16:26:57.771938+00:00', 
                'frozen-pipe-pet-protect': True, 
                'level': None, 
                'occupancy-mode': 'Flair Auto', 
                'set-point-manual': True, 
                'preheat-precool': True, 
                'current-humidity': 28.0, 
                'temp-away-max-c': 22.5, 
                'hold-reason': 'Set by Dale', 
                'current-temperature-c': 17.73, 
                'air-return': False, 
                'heat-cool-mode': 'HEAT', 
                'hold-until': None, 
                'room-away-mode': 'Smart Away', 
                'humidity-away-min': 10}
                '''
                LOGGER.debug('RAW Room: {}'.format(room.attributes))
                strHashRoom = str(int(hashlib.md5(room.attributes['name'].encode('utf8')).hexdigest(), 16) % (10 ** 8))
                rnode = self.poly.getNode(strHashRoom)

                # temperature (c and f), humidity, setpoint 
                rnode.new_update(room.attributes['current-temperature-c'], room.attributes['current-humidity'], room.attributes['set-point-c'])


            '''
            Not sure why this is being done.  As far as I can tell, these values
            are never queried after discovery.
            '''
            if  self.objStructure.attributes['is-active'] is True:
                self.setDriver('GV2', 1)
            else:
                self.setDriver('GV2', 0)
            
            tempC = float(self.objStructure.attributes['set-point-temperature-c'])
            tempF = (tempC * 9/5) + 32
            LOGGER.error('STRUCTURE: {} / {} / {} -- {}'.format(self.name, tempC, tempF, self.objStructure.attributes['created-at']))
            
            self.setDriver('CLISPC', round(tempC,1))
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
            
    drivers = [{'driver': 'GV2', 'value': 0, 'uom': 2, 'name': 'Status'},
               {'driver': 'CLISPC', 'value': 0, 'uom': 4, 'name': 'Setpoint C'},
               {'driver': 'GV3', 'value': 0, 'uom': 2, 'name': 'Home'},
               {'driver': 'GV4', 'value': 0, 'uom': 25, 'name': 'Mode'},
               {'driver': 'GV5', 'value': 0, 'uom': 25, 'name': 'Away Mode'},
               {'driver': 'GV6', 'value': 0, 'uom': 25, 'name': 'Setpoint Mode'},
               {'driver': 'GV7', 'value': 0, 'uom': 17, 'name': 'Setpoint F'} ]
    
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
        '''
        From what I can tell objVent is the data we got during discovery. 
        We really need to make a call to the API to get updated data and
        use that.

        objVent.get_rel() seems to get updated data (I.E. calls the API)
        but it doesn't seem to populate objVent.attributes with it.
          - duct-temperature-c
          - duct-pressure
          - precent-open
          - system-voltage
          - rssi
        '''

        try:
            if  self.objVent.attributes['inactive'] is True:
                self.setDriver('GV2', 1)
            else:
                self.setDriver('GV2', 0)

            # Get current-reading
            creading = self.objVent.get_rel('current-reading')
            cat = creading.attributes
            LOGGER.debug('VENT raw = {}'.format(cat))
            LOGGER.info('VENT: {} - {} {} {} {} {} {}'.format(self.name, cat['duct-temperature-c'], cat['duct-pressure'], cat['percent-open'], cat['system-voltage'], cat['rssi'], cat['created-at']))

            self.setDriver('GV1', cat['percent-open'])
            self.setDriver('GV8', cat['system-voltage'])

            self.setDriver('GV9', cat['duct-pressure'])
            
            if 'duct-temperature-c' in cat:
                tempC = float(cat['duct-temperature-c'])
                tempF = (tempC * 9/5) + 32
            
                self.setDriver('GV10', round(tempC,2))
                self.setDriver('GV11', round(tempF,2))

            self.setDriver('GV12', cat['rssi'])
        
        except ApiError as ex:
            LOGGER.error('Error query: %s', str(ex))
        except Exception as err:
            LOGGER.error('Error vent update: %s', str(err))
             
    drivers = [{'driver': 'GV2', 'value': 0, 'uom': 2, 'name': 'Status'},
               {'driver': 'GV1', 'value': 0, 'uom': 51, 'name': 'Open'},
               {'driver': 'GV8', 'value': 0, 'uom': 72, 'name': 'Voltage'},
               {'driver': 'GV9', 'value': 0, 'uom': 31, 'name': 'Pressure'},
               {'driver': 'GV10', 'value': 0, 'uom': 4, 'name': 'Temperature C'},
               {'driver': 'GV11', 'value': 0, 'uom': 17, 'name': 'Temperature F'},
               {'driver': 'GV12', 'value': 0, 'uom': 56, 'name': 'rssi'}]
    
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

            #LOGGER.debug('puck attributes: {}'.format(self.objPuck.attributes))
            #tempC = float(self.objPuck.attributes['current-temperature-c'])  if self.objPuck.attributes['current-temperature-c'] != None else 0 
            #tempF = (tempC * 9/5) + 32
                
            
            # Get current-reading
            creading = self.objPuck.get_rel('current-reading')
            cat = creading.attributes
            LOGGER.debug('PUCK raw = {}'.format(cat))

            if 'room-temperature-c' in cat:
                tempC = float(cat['room-temperature-c'])
                tempF = (tempC * 9/5) + 32
            else:
                tempC = 0
                tempF = 32

            LOGGER.info('PUCK: {} - {} / {} -- {}  {} {} {}'.format(self.name, tempC, tempF, cat['created-at'], cat['humidity'], cat['rssi'], cat['system-voltage']))

            self.setDriver('CLITEMP', round(tempC,1))
            self.setDriver('GV7', round(tempF,1))
            self.setDriver('CLIHUM', cat['humidity'])
            self.setDriver('GV12', cat['rssi'])
            self.setDriver('GV8', cat['system-voltage'])
               
        except ApiError as ex:
            LOGGER.error('Error query: %s', str(ex))  
        except Exception as err:
            LOGGER.error('Error puck update: %s', str(err))
            
    drivers = [ {'driver': 'GV2', 'value': 0, 'uom': 2, 'name': 'Status'},
               {'driver': 'CLITEMP', 'value': 0, 'uom': 4, 'name': 'Temperature C'},
               {'driver': 'CLIHUM', 'value': 0, 'uom': 51, 'name': 'Humidity'},
               {'driver': 'GV7', 'value': 0, 'uom': 17, 'name': 'Temperature F'},
               {'driver': 'GV8', 'value': 0, 'uom': 72, 'name': 'Voltage'},
               {'driver': 'GV12', 'value': 0, 'uom': 56, 'name': 'rssi'}]
    
    id = 'FLAIR_PUCK'
    commands = {  'QUERY': query }

class FlairRoom(udi_interface.Node):

    def __init__(self, controller, primary, address, name,room):

        super(FlairRoom, self).__init__(controller, primary, address, name)
        self.queryON = False
        self.name = name
        self.objRoom = room
        
    def query(self):
        self.reportDrivers()
    
    def new_update(self, tempC, humidity, setpoint):
        try:
            if self.objRoom.attributes['active'] is True:
                self.setDriver('GV2', 0)
            else:
                self.setDriver('GV2', 1)

            LOGGER.info('ROOM: {} {} / {} / {}'.format(self.name, tempC, humidity, setpoint))

            if tempC is not None:
                tempF = (tempC * 9/5) + 32
                self.setDriver('CLITEMP', round(tempC,1))
                self.setDriver('GV7',round(tempF,1))
            if humidity is None:
                self.setDriver('CLIHUM',0)
            else:
                self.setDriver('CLIHUM', humidity)

            if setpoint is not None:
                self.setDriver('CLISPC', round(setpoint,1))
            else:
                self.setDriver('CLISPC', 0)
        except Exception as err:
            LOGGER.error('Error room update: %s', str(err))

    def update(self):
        LOGGER.debug('update not implemented this way')

    def old_update(self):
        '''
        Should we try:  creading = self.objRoom.get_rel()
        That doesn't seem to work
        '''
        try:
            if self.objRoom.attributes['active'] is True:
                self.setDriver('GV2', 0)
            else:
                self.setDriver('GV2', 1)

            if self.objRoom.attributes['current-temperature-c'] is not None :
                
                tempC = float(self.objRoom.attributes['current-temperature-c']) if self.objRoom.attributes['current-temperature-c'] != None else 0 
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
        except Exception as err:
            LOGGER.error('Error room update: %s', str(err))
    
    def setTemp(self, command):
        try:
            self.objRoom.update(attributes={'set-point-c': command.get('value')})
            self.setDriver('CLISPC', round(self.objRoom.attributes['set-point-c'],1))

        except ApiError as ex:
            LOGGER.error('Error setTemp: %s', str(ex))

    drivers = [ {'driver': 'GV2', 'value': 0, 'uom': 2, 'name': 'Status'},
               {'driver': 'CLITEMP', 'value': 0, 'uom': 4, 'name': 'Temperature C'},
               {'driver': 'CLIHUM', 'value': 0, 'uom': 51, 'name': 'Humidity'},
               {'driver': 'CLISPC', 'value': 0, 'uom': 4, 'name': 'Setpoint'},
               {'driver': 'GV7', 'value': 0, 'uom': 17, 'name': 'Temperature F'}]
    
    id = 'FLAIR_ROOM'
    commands = { 'QUERY': query, 
                 'SET_TEMP': setTemp }    
    
if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start(VERSION)
        Controller(polyglot, 'controller', 'controller', 'FlairNodeServer')
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
