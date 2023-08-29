""""Utilities for evaluating FeatureScripts against part studios."""


from concurrent import futures
import dataclasses
import pathlib
from typing import Iterable, TypedDict
from library.api import api_base, api_path
from library.api.endpoints import part_studios

SCRIPT_PATH = pathlib.Path("../scripts")


def open_script(script_name: str):
    with (SCRIPT_PATH / pathlib.Path("{}.fs".format(script_name))).open() as file:
        return file.read()


class AutoAssemblyBase(TypedDict):
    mate_id: str
    target: api_path.ElementPath


class AutoAssemblyTarget(TypedDict):
    mate_id: str


def evalute_auto_assembly_part(
    api: api_base.Api, part_studio_path: api_path.ElementPath
) -> dict:
    return part_studios.evaluate_feature_script(
        api, part_studio_path, open_script("parseAutoAssembly")
    )


def evalute_auto_assembly_target_part(
    api: api_base.Api, part_studio_path: api_path.ElementPath
) -> dict:
    return part_studios.evaluate_feature_script(
        api, part_studio_path, open_script("parseAutoAssemblyTarget")
    )


def evaluate_assembly_mirror_part(
    api: api_base.Api, part_studio_path: api_path.ElementPath
) -> dict:
    return part_studios.evaluate_feature_script(
        api, part_studio_path, open_script("parseAssemblyMirror")
    )


@dataclasses.dataclass
class EvaluateAssemblyMirrorResult:
    """
    Attributes:
        base_to_target_mates: A dict mapping base ids to target ids.
        origin_base_mates: A set of mate ids representing parts to mirror.
    """

    base_to_target_mates: dict[str, str]
    origin_base_mates: set[str]

    def instances_to_instantiate(
        self, mates_to_parts: dict[str, api_path.PartPath]
    ) -> dict[api_path.PartPath, int]:
        """Generates a dict of part paths representing parts which need to be copied.

        Returns:
            A dict mapping part paths to the number of times that part path should be instantiated.
        """
        base_mate_ids = list(self.origin_base_mates)
        base_mate_ids.extend(self.base_to_target_mates.values())
        return dict()


def evaluate_assembly_mirror_parts(
    api: api_base.Api, part_studio_paths: Iterable[api_path.ElementPath]
):
    with futures.ThreadPoolExecutor() as executor:
        threads = [
            executor.submit(evaluate_assembly_mirror_part, api, part_studio_path)
            for part_studio_path in part_studio_paths
        ]

        base_to_target_mates = dict()
        origin_base_mates = set()

        for future in futures.as_completed(threads):
            script_results = future.result()
            if not script_results["valid"]:
                continue
            for script_result in script_results["mirrors"]:
                if script_result["mateToOrigin"]:
                    origin_base_mates.add(script_result["baseMateId"])
                else:
                    base_to_target_mates[script_result["baseMateId"]] = script_result[
                        "targetMateId"
                    ]

        return EvaluateAssemblyMirrorResult(base_to_target_mates, origin_base_mates)


@dataclasses.dataclass
class PartMaps:
    mates_to_targets: dict[str, api_path.ElementPath] = dataclasses.field(
        default_factory=dict
    )
    mirror_mates: dict[str, str] = dataclasses.field(default_factory=dict)
    origin_mirror_mates: set[str] = dataclasses.field(default_factory=set)


def evalute_auto_assembly_parts(
    api: api_base.Api, part_studio_paths: set[api_path.ElementPath]
):
    with futures.ThreadPoolExecutor() as executor:
        threads = [
            executor.submit(evalute_auto_assembly_part, api, part_studio_path)
            for part_studio_path in part_studio_paths
        ]

        part_maps = PartMaps()
        for future in futures.as_completed(threads):
            result = future.result()
            if not result["valid"]:
                continue

            for values in result["mates"]:
                part_maps.mates_to_targets[
                    values["mateId"]
                ] = api_path.make_element_path_from_obj(values)

        return part_maps


def evaluate_targets(
    api: api_base.Api, mates_to_targets: dict[str, api_path.ElementPath]
) -> dict[str, str]:
    """Converts a dict mapping mate_ids to target part studios into a dict mapping target part studio mate ids to original mate ids.

    Args:
        mates_to_targets: A mapping of mate ids to the target part studio to evaluate.
    Returns:
        A mapping of target mate ids to original mate ids.

    TODO: Deduplicate target part studios and re-associate the data afterwards."""
    with futures.ThreadPoolExecutor() as executor:
        threads = {
            executor.submit(
                evalute_auto_assembly_target_part, api, part_studio_path
            ): target_mate_id
            for target_mate_id, part_studio_path in mates_to_targets.items()
        }

        targets_to_mate_connectors = {}
        for future in futures.as_completed(threads):
            result = future.result()
            target_mate_id = threads[future]
            targets_to_mate_connectors[target_mate_id] = result["targetMateId"]
        return targets_to_mate_connectors
