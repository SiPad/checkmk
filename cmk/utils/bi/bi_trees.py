#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2020 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from typing import List, Optional, Any, Set, Dict, Tuple, Union, Type
from marshmallow import fields, pre_dump
from marshmallow_oneofschema import OneOfSchema  # type: ignore[import]

from livestatus import SiteId

from cmk.gui.i18n import _  # pylint: disable=cmk-module-layer-violation
import cmk.utils.defines
from cmk.utils.type_defs import (
    HostName,
    ServiceName,
    HostState,
    ServiceState,
)

from cmk.utils.bi.bi_lib import (
    BIStates,
    BIServiceWithFullState,
    BIHostStatusInfoRow,
    BIHostSpec,
    ReqConstant,
    ReqNested,
    ReqString,
    ReqList,
    create_nested_schema_for_class,
    ABCBICompiledNode,
    ABCBIAggregationFunction,
    ABCBIStatusFetcher,
    ABCBISearcher,
    BIAggregationGroups,
    BIAggregationComputationOptions,
    RequiredBIElement,
    NodeComputeResult,
    NodeResultBundle,
)
from cmk.utils.bi.bi_rule_interface import BIRuleProperties
from cmk.utils.caching import instance_method_lru_cache

from cmk.utils.bi.bi_aggregation_functions import BIAggregationFunctionSchema
from cmk.utils.bi.bi_node_vis import (
    BINodeVisLayoutStyleSchema,
    BIAggregationVisualizationSchema,
    BINodeVisBlockStyleSchema,
)
from cmk.utils.bi.bi_schema import Schema

#   .--Leaf----------------------------------------------------------------.
#   |                         _                __                          |
#   |                        | |    ___  __ _ / _|                         |
#   |                        | |   / _ \/ _` | |_                          |
#   |                        | |__|  __/ (_| |  _|                         |
#   |                        |_____\___|\__,_|_|                           |
#   |                                                                      |
#   +----------------------------------------------------------------------+


class BICompiledLeaf(ABCBICompiledNode):
    @classmethod
    def type(cls) -> str:
        return "leaf"

    def __init__(self,
                 host_name: HostName,
                 service_description: Optional[ServiceName] = None,
                 site_id=None,
                 **kwargs):
        super().__init__()
        self.required_hosts = [(site_id, host_name)]
        self.site_id = site_id
        self.host_name = host_name
        self.service_description = service_description

    def _get_comparable_name(self) -> str:
        return ":".join([self.site_id or "", self.host_name, self.service_description or ""])

    def parse_schema(self, schema_config: Dict) -> None:
        self.site_id = schema_config["site_id"]
        self.host_name = schema_config["host_name"]
        self.service_description = schema_config["service_description"]

    def services_of_host(self, host_name: HostName) -> Set[ServiceName]:
        if host_name == self.host_name and self.service_description:
            return {self.service_description}
        return set()

    def compile_postprocess(
        self,
        bi_branch_root: ABCBICompiledNode,
        services_of_host: Dict[HostName, Set[ServiceName]],
        bi_searcher: ABCBISearcher,
    ) -> List[ABCBICompiledNode]:
        return [self]

    @instance_method_lru_cache()
    def required_elements(self) -> Set[RequiredBIElement]:
        return {RequiredBIElement(self.site_id, self.host_name, self.service_description)}

    def __str__(self):
        return "BICompiledLeaf[Site %s, Host: %s, Service %s]" % (self.site_id, self.host_name,
                                                                  self.service_description)

    def compute(self,
                computation_options: BIAggregationComputationOptions,
                bi_status_fetcher: ABCBIStatusFetcher,
                use_assumed=False) -> Optional[NodeResultBundle]:
        entity = self._get_entity(bi_status_fetcher)
        if not entity or entity.state is None or entity.hard_state is None:
            # Note: An entity state of None may be generated by the availability
            #       There might be service information, but no host information available
            #       A state of None will be treated as "missing"
            return None

        # Downtime
        downtime_state = 0
        if entity.scheduled_downtime_depth != 0:
            downtime_state = 1 if computation_options.escalate_downtimes_as_warn else 2

        # State
        if entity.has_been_checked:
            state = entity.hard_state if computation_options.use_hard_states else entity.state
            # Since we need an equalized state mapping, map host state DOWN to CRIT
            if self.service_description is None:
                state = self._map_hoststate_to_bistate(state)
        else:
            state = BIStates.PENDING

        # Assumed
        assumed_result = None
        if use_assumed:
            assumed_state = bi_status_fetcher.assumed_states.get(
                (self.site_id, self.host_name, self.service_description))
            if assumed_state is not None:
                assumed_result = NodeComputeResult(
                    int(assumed_state),
                    downtime_state,
                    bool(entity.acknowledged),
                    _("Assumed to be %s" % self._get_state_name(assumed_state)),
                    entity.in_service_period,
                    {},
                    {},
                )

        return NodeResultBundle(
            NodeComputeResult(
                state,
                downtime_state,
                bool(entity.acknowledged),
                entity.plugin_output,
                bool(entity.in_service_period),
                {},
                {},
            ),
            assumed_result,
            [],
            self,
        )

    def _map_hoststate_to_bistate(self, host_state: HostState):
        if host_state == BIStates.HOST_UP:
            return BIStates.OK
        if host_state == BIStates.HOST_DOWN:
            return BIStates.CRIT
        if host_state == BIStates.HOST_UNREACHABLE:
            return BIStates.UNKNOWN
        return BIStates.UNKNOWN

    def _get_state_name(self, state: Union[HostState, ServiceState]) -> str:
        if self.service_description:
            return cmk.utils.defines.service_state_name(state)
        return cmk.utils.defines.host_state_name(state)

    def _get_entity(
            self,
            bi_status_fetcher) -> Optional[Union[BIHostStatusInfoRow, BIServiceWithFullState]]:
        entity = bi_status_fetcher.states.get((self.site_id, self.host_name))
        if not entity:
            return None
        if self.service_description is None:
            return entity
        return entity.services_with_fullstate.get(self.service_description)

    @classmethod
    def schema(cls) -> Type["BICompiledLeafSchema"]:
        return BICompiledLeafSchema

    def serialize(self):
        return {
            "type": self.type(),
            "required_hosts": list(
                map(lambda x: {
                    "site_id": x[0],
                    "host_name": x[1]
                }, self.required_hosts)),
            "site_id": self.site_id,
            "host_name": self.host_name,
            "service_description": self.service_description,
        }


class BISiteHostPairSchema(Schema):
    site_id = ReqString()
    host_name = ReqString()

    @pre_dump
    def pre_dumper(self, obj: Tuple, many=False) -> Dict:
        # Convert aggregations and rules to list
        return {"site_id": obj[0], "host_name": obj[1]}


class BICompiledLeafSchema(Schema):
    type = ReqConstant(BICompiledLeaf.type())
    required_hosts = ReqList(fields.Nested(BISiteHostPairSchema))
    site_id = ReqString()
    host_name = ReqString()
    service_description = fields.String()


#   .--Rule----------------------------------------------------------------.
#   |                         ____        _                                |
#   |                        |  _ \ _   _| | ___                           |
#   |                        | |_) | | | | |/ _ \                          |
#   |                        |  _ <| |_| | |  __/                          |
#   |                        |_| \_\\__,_|_|\___|                          |
#   |                                                                      |
#   +----------------------------------------------------------------------+


class BICompiledRule(ABCBICompiledNode):
    @classmethod
    def type(cls) -> str:
        return "rule"

    def __init__(
        self,
        rule_id: str,
        pack_id: str,
        nodes: List[ABCBICompiledNode],
        required_hosts: List[Tuple[SiteId, HostName]],
        properties: BIRuleProperties,
        aggregation_function: ABCBIAggregationFunction,
        node_visualization: Dict[str, Any],
    ):
        super().__init__()
        self.id = rule_id
        self.pack_id = pack_id
        self.required_hosts = required_hosts
        self.nodes = nodes
        self.properties = properties
        self.aggregation_function = aggregation_function
        self.node_visualization = node_visualization

    def __str__(self):
        return "BICompiledRule[%s, %d rules, %d leaves %d remaining]" % (
            self.properties.title,
            len([x for x in self.nodes if x.type() == "rule"]),
            len([x for x in self.nodes if x.type() == "leaf"]),
            len([x for x in self.nodes if x.type() == "remaining"]),
        )

    def _get_comparable_name(self) -> str:
        return self.properties.title

    def compile_postprocess(self, bi_branch_root: ABCBICompiledNode,
                            services_of_host: Dict[HostName, Set[ServiceName]],
                            bi_searcher: ABCBISearcher) -> List[ABCBICompiledNode]:
        self.nodes = [
            res for node in self.nodes
            for res in node.compile_postprocess(bi_branch_root, services_of_host, bi_searcher)
        ]
        return [self]

    def services_of_host(self, host_name: HostName) -> Set[ServiceName]:
        return {result for node in self.nodes for result in node.services_of_host(host_name)}

    @instance_method_lru_cache()
    def required_elements(self) -> Set[RequiredBIElement]:
        return {result for node in self.nodes for result in node.required_elements()}

    def get_required_hosts(self) -> Set[BIHostSpec]:
        return {
            BIHostSpec(element.site_id, element.host_name) for element in self.required_elements()
        }

    def compute(self,
                computation_options: BIAggregationComputationOptions,
                bi_status_fetcher: ABCBIStatusFetcher,
                use_assumed=False) -> Optional[NodeResultBundle]:
        bundled_results = [
            bundle for bundle in [
                node.compute(computation_options, bi_status_fetcher, use_assumed)
                for node in self.nodes
            ] if bundle is not None
        ]
        if not bundled_results:
            return None
        actual_result = self._process_node_compute_result(
            [x.actual_result for x in bundled_results], computation_options)

        if not use_assumed:
            return NodeResultBundle(actual_result, None, bundled_results, self)

        assumed_result_items = []
        for bundle in bundled_results:
            assumed_result_items.append(bundle.assumed_result if bundle.
                                        assumed_result is not None else bundle.actual_result)
        assumed_result = self._process_node_compute_result(assumed_result_items,
                                                           computation_options)
        return NodeResultBundle(actual_result, assumed_result, bundled_results, self)

    def _process_node_compute_result(
            self, results: List[NodeComputeResult],
            computation_options: BIAggregationComputationOptions) -> NodeComputeResult:
        state = self.aggregation_function.aggregate([result.state for result in results])

        downtime_state = self.aggregation_function.aggregate(
            [result.downtime_state for result in results])
        if downtime_state > 0:
            downtime_state = 2 if computation_options.escalate_downtimes_as_warn else 1

        is_acknowledged = False
        if state != 0:
            is_acknowledged = self.aggregation_function.aggregate(
                [0 if result.acknowledged else result.state for result in results]) == 0

        in_service_period = self.aggregation_function.aggregate(
            [0 if result.in_service_period else 2 for result in results]) == 0

        return NodeComputeResult(
            state,
            downtime_state,
            is_acknowledged,
            # TODO: fix str casting in later commit
            self.properties.state_messages.get(str(state), ""),
            in_service_period,
            self.properties.state_messages,
            {},
        )

    @classmethod
    def schema(cls) -> Type["BICompiledRuleSchema"]:
        return BICompiledRuleSchema

    def serialize(self):
        return {
            "id": self.id,
            "pack_id": self.pack_id,
            "type": self.type(),
            "required_hosts": list(
                map(lambda x: {
                    "site_id": x[0],
                    "host_name": x[1]
                }, self.required_hosts)),
            "nodes": [node.serialize() for node in self.nodes],
            "aggregation_function": self.aggregation_function.serialize(),
            "node_visualization": self.node_visualization,
            "properties": self.properties.serialize(),
        }


class BICompiledRuleSchema(Schema):
    id = ReqString()
    pack_id = ReqString()
    type = ReqConstant(BICompiledRule.type())
    required_hosts = ReqList(fields.Nested(BISiteHostPairSchema))
    nodes = ReqList(fields.Nested("BIResultSchema"))
    aggregation_function = ReqNested(
        BIAggregationFunctionSchema,
        example={
            "type": "worst",
            "count": 2,
            "restrict_state": 1
        },
    )
    node_visualization = ReqNested(BINodeVisLayoutStyleSchema,
                                   example=BINodeVisBlockStyleSchema().dump({}))
    properties = ReqNested("BIRulePropertiesSchema", example={})


#   .--Remaining-----------------------------------------------------------.
#   |           ____                      _       _                        |
#   |          |  _ \ ___ _ __ ___   __ _(_)_ __ (_)_ __   __ _            |
#   |          | |_) / _ \ '_ ` _ \ / _` | | '_ \| | '_ \ / _` |           |
#   |          |  _ <  __/ | | | | | (_| | | | | | | | | | (_| |           |
#   |          |_| \_\___|_| |_| |_|\__,_|_|_| |_|_|_| |_|\__, |           |
#   |                                                     |___/            |
#   +----------------------------------------------------------------------+


class BIRemainingResult(ABCBICompiledNode):
    # The BIRemainingResult lacks a serializable schema, since it is resolved into
    # BICompiledLeaf(s) during the compilation
    @classmethod
    def type(cls) -> str:
        return "remaining"

    def __init__(self, host_names: List[HostName]):
        super().__init__()
        self.host_names = host_names

    def _get_comparable_name(self) -> str:
        return ""

    def compile_postprocess(self, bi_branch_root: ABCBICompiledNode,
                            services_of_host: Dict[HostName, Set[ServiceName]],
                            bi_searcher: ABCBISearcher) -> List[ABCBICompiledNode]:
        postprocessed_nodes: List[ABCBICompiledNode] = []
        for host_name in self.host_names:
            site_id = bi_searcher.hosts[host_name].site_id
            used_services = services_of_host.get(host_name, set())
            for service_description in set(bi_searcher.hosts[host_name].services) - used_services:
                postprocessed_nodes.append(
                    BICompiledLeaf(host_name=host_name,
                                   service_description=service_description,
                                   site_id=site_id))
        postprocessed_nodes.sort()
        return postprocessed_nodes

    @instance_method_lru_cache()
    def required_elements(self) -> Set[RequiredBIElement]:
        return set()

    def services_of_host(self, host_name: HostName) -> Set[ServiceName]:
        return set()

    def compute(self,
                computation_options: BIAggregationComputationOptions,
                bi_status_fetcher: ABCBIStatusFetcher,
                use_assumed=False) -> Optional[NodeResultBundle]:
        return None

    def serialize(self) -> Dict[str, Any]:
        return {}


#   .--Aggregation---------------------------------------------------------.
#   |         _                                    _   _                   |
#   |        / \   __ _  __ _ _ __ ___  __ _  __ _| |_(_) ___  _ __        |
#   |       / _ \ / _` |/ _` | '__/ _ \/ _` |/ _` | __| |/ _ \| '_ \       |
#   |      / ___ \ (_| | (_| | | |  __/ (_| | (_| | |_| | (_) | | | |      |
#   |     /_/   \_\__, |\__, |_|  \___|\__, |\__,_|\__|_|\___/|_| |_|      |
#   |             |___/ |___/          |___/                               |
#   +----------------------------------------------------------------------+


class BICompiledAggregation:
    def __init__(
        self,
        aggregation_id: str,
        branches: List[BICompiledRule],
        computation_options: BIAggregationComputationOptions,
        aggregation_visualization: Dict[str, Any],
        groups: BIAggregationGroups,
    ):
        self.id = aggregation_id
        self.branches = branches
        self.computation_options = computation_options
        self.aggregation_visualization = aggregation_visualization
        self.groups = groups

    def compute_branches(self, branches: List[BICompiledRule],
                         bi_status_fetcher: ABCBIStatusFetcher) -> List[NodeResultBundle]:
        assumed_state_ids = set(bi_status_fetcher.assumed_states)
        aggregation_results = []
        for bi_compiled_branch in branches:
            required_elements = bi_compiled_branch.required_elements()
            compute_assumed_state = any(assumed_state_ids.intersection(required_elements))
            result = bi_compiled_branch.compute(self.computation_options,
                                                bi_status_fetcher,
                                                use_assumed=compute_assumed_state)
            if result is not None:
                aggregation_results.append(result)
        return aggregation_results

    def convert_result_to_legacy_format(self, node_result_bundle: NodeResultBundle) -> Dict:
        def generate_state(item):
            if not item:
                return None
            return {
                "state": item.state,
                "acknowledged": item.acknowledged,
                "in_downtime": item.downtime_state > 0,
                "in_service_period": item.in_service_period,
                "output": item.output,
            }

        def create_tree_state(bundle: NodeResultBundle, is_toplevel=False):
            response = []
            response.append(generate_state(bundle.actual_result))
            response.append(generate_state(bundle.assumed_result))
            if is_toplevel:
                response.append(self.create_aggr_tree(bundle.instance))
            else:
                response.append(self.eval_result_node(bundle.instance))
            if bundle.nested_results:
                response.append(list(map(create_tree_state, bundle.nested_results)))
            return tuple(response)

        bi_compiled_branch = node_result_bundle.instance

        response = {
            "aggr_tree": self.create_aggr_tree(bi_compiled_branch),
            "aggr_treestate": create_tree_state(node_result_bundle, is_toplevel=True),
            "aggr_state": generate_state(node_result_bundle.actual_result),
            "aggr_assumed_state": generate_state(node_result_bundle.assumed_result),
            "aggr_effective_state":
                generate_state(node_result_bundle.assumed_result if node_result_bundle.
                               assumed_result else node_result_bundle.actual_result),
            "aggr_name": bi_compiled_branch.properties.title,
            "aggr_output": node_result_bundle.actual_result.output,
            "aggr_hosts": bi_compiled_branch.required_hosts,
            "aggr_type": "multi",
            "aggr_group": "dummy",  # dummy, will be set later on within the old bi madness
            # Required in availability
            "aggr_compiled_aggregation": self,
            "aggr_compiled_branch": bi_compiled_branch,
        }

        response["tree"] = response["aggr_tree"]
        return response

    def create_aggr_tree(self, bi_compiled_branch: BICompiledRule) -> Dict:
        response = self.eval_result_node(bi_compiled_branch)
        response["aggr_group_tree"] = self.groups.names
        response["aggr_group_tree"] += ["/".join(x) for x in self.groups.paths]
        response["aggr_type"] = "multi"
        response["aggregation_id"] = self.id
        response["downtime_aggr_warn"] = self.computation_options.escalate_downtimes_as_warn
        response["use_hard_states"] = self.computation_options.use_hard_states
        response["node_visualization"] = self.aggregation_visualization
        return response

    def eval_result_node(self, node: ABCBICompiledNode) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if isinstance(node, BICompiledLeaf):
            result["type"] = 1
            result["host"] = (node.site_id, node.host_name)
            if node.service_description:
                result["service"] = node.service_description

            result["reqhosts"] = list(node.required_hosts)
            result["title"] = node.host_name if node.service_description is None else "%s - %s" % (
                node.host_name, node.service_description)
            return result

        if isinstance(node, BICompiledRule):
            result["type"] = 2
            result["title"] = node.properties.title
            result["rule_id"] = node.id
            result["reqhosts"] = list(node.required_hosts)
            result["nodes"] = list(map(self.eval_result_node, node.nodes))
            result["rule_layout_style"] = node.node_visualization
            if node.properties.icon:
                result["icon"] = node.properties.icon
            return result

        raise NotImplementedError("Unknown node type %r" % node)

    @classmethod
    def schema(cls) -> Type["BICompiledAggregationSchema"]:
        return BICompiledAggregationSchema

    def serialize(self):
        return {
            "id": self.id,
            "branches": [branch.serialize() for branch in self.branches],
            "aggregation_visualization": self.aggregation_visualization,
            "computation_options": self.computation_options.serialize(),
            "groups": self.groups.serialize(),
        }


class BICompiledAggregationSchema(Schema):
    id = ReqString()
    branches = ReqList(fields.Nested(BICompiledRuleSchema))
    aggregation_visualization = ReqNested(BIAggregationVisualizationSchema)
    computation_options = create_nested_schema_for_class(
        BIAggregationComputationOptions,
        example_config={"disabled": True},
    )

    groups = create_nested_schema_for_class(
        BIAggregationGroups,
        example_config={
            "names": ["groupA", "groupB"],
            "paths": [["path", "group", "a"]]
        },
    )


class BIResultSchema(OneOfSchema):
    type_field = "type"
    type_field_remove = False
    type_schemas = {
        "leaf": BICompiledLeafSchema,
        "rule": BICompiledRuleSchema,
    }

    def get_obj_type(self, obj: ABCBICompiledNode) -> str:
        return obj.type()
