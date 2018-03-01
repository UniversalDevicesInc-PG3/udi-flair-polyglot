# Flair Polyglot V2 Node Server

![Build Status](https://travis-ci.org/therealmysteryman/udi-flair-polyglot.svg?branch=master)

This Poly provides an interface between Flair Vents and Polyglot v2 server. Has been testing with Puck in Gateway and Vent on HVAC system. https://flair.co/

#### Installation

Installation instructions

You can install from Polyglot V2 store or manually : 

1. cd ~/.polyglot/nodeservers
2. git clone https://github.com/therealmysteryman/udi-flair-polyglot.git
3. run ./install.sh to install the required dependency.
4. Add a custom variable named host containing the client_id and client_secret. Those value need to be requested to Flair Support.

#### Source

1. Based on the Node Server Template - https://github.com/Einstein42/udi-poly-template-python
2. Using the Flair Client API - https://github.com/flair-systems/flair-api-client-py
