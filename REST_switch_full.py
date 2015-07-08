# Based on https://github.com/castroflavio/ryu/blob/master/ryu/app/rest.py
# simple switch application with REST api

import json
from webob import Response
import OSPF_switch
from ryu.topology import switches
from ryu.app import wsgi as wsgi_app
from ryu.base import app_manager
from ryu.app.wsgi import ControllerBase, WSGIApplication
from ryu.controller import network
from ryu.exception import NetworkNotFound, NetworkAlreadyExist
from ryu.exception import PortNotFound, PortAlreadyExist
from ryu.lib import dpid as dpid_lib
from ryu.lib import mac as mac_lib


class Rest_controller(OSPF_switch.ospf_switch):
    def __init__(self, req, link, data, **config):
        super(Rest_controller, self).__init__(req, link, data, **config)
        self.nw = data

    def create(self, req, network_id, **_kwargs):
        try:
            self.nw.create_network(network_id)
        except NetworkAlreadyExist:
            return Response(status=409)
        else:
            return Response(status=200)

    def update(self, req, network_id, **_kwargs):
        self.nw.update_network(network_id)
        return Response(status=200)

    def lists(self, req, **_kwargs):
        body = json.dumps(self.nw.list_networks())
        return Response(content_type='application/json', body=body)

    def delete(self, req, network_id, **_kwargs):
        try:
            self.nw.remove_network(network_id)
        except NetworkNotFound:
            return Response(status=404)
        return Response(status=200)


class Rest_ports(OSPF_switch.ospf_switch):
    def __init__(self, req, link, data, **config):
        super(Rest_ports, self).__init__(req, link, data, **config)
        self.nw = data

    def create(self, req, network_id, dpid, port_id, **_kwargs):
        dpid = dpid_lib.str_to_dpid(dpid)
        port_id = int(port_id)
        try:
            self.nw.create_port(network_id, dpid, port_id)
        except NetworkNotFound:
            return Response(status=404)
        except PortAlreadyExist:
            return Response(status=409)

        return Response(status=200)

    def update(self, req, network_id, dpid, port_id, **_kwargs):
        dpid = dpid_lib.str_to_dpid(dpid)
        port_id = int(port_id)
        try:
            self.nw.update_port(network_id, dpid, port_id)
        except NetworkNotFound:
            return Response(status=404)
        return Response(status=200)

    def lists(self, req, network_id, **_kwargs):
        try:
            body = json.dumps(self.nw.list_ports(network_id))
        except NetworkNotFound:
            return Response(status=404)

        return Response(content_type='application/json', body=body)

    def delete(self, req, network_id, dpid, port_id, **_kwargs):
        dpid = dpid_lib.str_to_dpid(dpid)
        port_id = int(port_id)
        try:
            self.nw.remove_port(network_id, dpid, port_id)
        except (NetworkNotFound, PortNotFound):
            return Response(status=404)

        return Response(status=200)


class Rest_mac(OSPF_switch.ospf_switch):
    def __init__(self, req, link, data, **config):
        super(Rest_mac, self).__init__(req, link, data, **config)
        self.nw = data

    def create(self, _req, network_id, dpid, port_id, mac_addr, **_kwargs):
        dpid = dpid_lib.str_to_dpid(dpid)
        port_id = int(port_id)
        mac_addr = mac_lib.haddr_to_bin(mac_addr)
        try:
            self.nw.create_mac(network_id, dpid, port_id, mac_addr)
        except PortNotFound:
            return Response(status=404)
        except network.MacAddressAlreadyExist:
            return Response(status=409)
        return Response(status=200)

    def update(self, _req, network_id, dpid, port_id, mac_addr, **_kwargs):
        dpid = dpid_lib.str_to_dpid(dpid)
        port_id = int(port_id)
        mac_addr = mac_lib.haddr_to_bin(mac_addr)
        try:
            self.nw.update_mac(network_id, dpid, port_id, mac_addr)
        except PortNotFound:
            return Response(status=404)
        return Response(status=200)

    def lists(self, _req, network_id, dpid, port_id, **_kwargs):
        dpid = dpid_lib.str_to_dpid(dpid)
        port_id = int(port_id)
        try:
            body = json.dumps([mac_lib.haddr_to_str(mac_addr) for mac_addr in
                               self.nw.list_mac(dpid, port_id)])
        except PortNotFound:
            return Response(status=404)
        return Response(content_type='application/json', body=body)


class RestAPI(app_manager.RyuApp):
    _CONTEXTS = {
        'network': network.Network,
        'wsgi': WSGIApplication
    }

    def __init__(self, *args, **kwargs):
        super(RestAPI, self).__init__(*args, **kwargs)
        self.nw = kwargs['network']
        wsgi = kwargs['wsgi']
        mapper = wsgi.mapper

        wsgi.registory['Rest_controller'] = self.nw
        route_name = 'networks'
        uri = '/v1.3/networks'
        mapper.connect(route_name, uri,
                       controller=Rest_controller, action='list',
                       conditions=dict(method=['GET', 'HEAD']))
        uri += '/{network_id}'
        s = mapper.submapper(controller=Rest_controller)
        s.connect(route_name, uri, action='create',
                  conditions=dict(method=['POST']))
        s.connect(route_name, uri, action='update',
                  conditions=dict(method=['PUT']))
        s.connect(route_name, uri, action='delete',
                  condition=dict(method=['DELETE']))

        wsgi.registory['Rest_ports'] = self.nw
        route_name = 'ports'
        mapper.connect(route_name, uri,
                       controller=Rest_ports, action='lists',
                       conditions=dict(method=['GET']))
        uri += '/{dpid}_{port_id}'
        requirements = {'dpid': dpid_lib.DPID_PATTERN,
                        'port_id': wsgi_app.DIGIT_PATTERN}
        s = mapper.submapper(controller=Rest_ports, requirements=requirements)
        s.connect(route_name, uri, action='create',
                  conditions=dict(method=['POST']))
        s.connect(route_name, uri, action='update',
                  conditions=dict(method=['PUT']))
        s.connect(route_name, uri, action='delete',
                  conditions=dict(method=['DELETE']))
        wsgi.registory['Rest_mac'] = self.nw
        route_name = 'macs'
        uri += '/macs'
        mapper.connect(route_name, uri,
                       controller=Rest_mac,
                       requirements=requirements)
        s.connect(route_name, uri, action='create',
                  conditions=dict(method=['POST']))
        s.connect(route_name, uri, action='update',
                  conditions=dict(method=['PUT']))
