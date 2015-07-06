import logging
import struct
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
import networkx as nx
from ryu.lib.mac import haddr_to_bin


class ospf_switch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ospf_switch, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.topology_api_app = self
        self.nx=nx.DiGraph()
        self.nodes = {}
        self.links = {}
        self.no_of_nodes = 0
        self.no_of_links = 0

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    #def add_flow(self, datapath, priority, match, actions, buffer_id=None):
    def add_flow(self, datapath, in_port, dst, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = datapath.ofproto_parser.OFPMatch(in_port=in_port,
                                                 dl_dst=haddr_to_bin(dst))

        #inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
        #                                     actions)]
        #if buffer_id:
        #    mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
        #                            priority=priority, match=match,
        #                            instructions=inst)
            #self.logger.info("The mod is $s", mod)
        #else:
        #    mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
        #                            match=match, instructions=inst)
            #self.logger.info("The mod is $r", mod)
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath,match=match, cookie=0,
            command=ofproto.OFPFC_ADD,idle_timeout=0, hard_timeout=0,
            priority=ofproto.OFP_DEFAULT_PRIORITY,
            flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        self.logger.info("mac_to_port %s", self.mac_to_port)

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        #self.logger.info('packet in %s %s %s %s', dpid, src, dst, in_port)
        self.mac_to_port[dpid][src] = in_port
#        self.logger.info("the msg is %s the datapath is %s the ofproto is %s the parser is %s the in_port is %s the pkt is %s the eth is %s the dst is %s the src is %s the dpid is %s the self is %s", msg, datapath, ofproto, parser, in_port, pkt, eth, dst, src, dpid, self)

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            #self.logger.info("output port is %s", out_port)
        else:
            out_port = ofproto.OFPP_FLOOD
            #self.logger.info("output port is %s", out_port)
        actions = [parser.OFPActionOutput(out_port)]
        if src not in self.net:
            self.net.add_node(src)
            self.net.add_edge(dpid,src,{'port':msg.in_port})
            self.net.add_edge(src, dpid)
        if dst in self.net:
            path = nx.shortest_path(self.net,src,dst)
            next = path[path.index(dpid)+1]
            out_port = self.net[dpid][next]['port']
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            self.add_flow(datapath, msg.in_port, dst, actions)

        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath,
                                                   buffer_id=msg.buffer_id,
                                                   in_port=msg.in_port,
                                                   actions=actions)
        datapath.send_msg(out)

    @set_ev_cls(event.EventSwitchEnter)
    def get_topology_data(self, ev):
        switch_list = get_switch(self.topology_api_app, None)
        switches = [switch.dp.id for switch in switch_list]
        self.net.add_nodes_from(switches)
        links_list = get_link(self.topology_api_app, None)
        links=[(link.src.dpid,link.dst.dpid, {'port': link.src.port_no}) for link in links_list]
        self.net.add_edges_from(links)
        links=[(link.dst.dpid,list.src.dpid, {'port': link.dst.port_no}) for link in links_list]
        self.net.add_edges_from(links)
        print "*********List of links"
        print self.net.edges()
