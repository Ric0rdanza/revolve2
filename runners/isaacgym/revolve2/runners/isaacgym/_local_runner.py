import math
import multiprocessing as mp
import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional

import colored
import numpy as np
from isaacgym import gymapi, gymutil
from pyrr import Quaternion, Vector3

from revolve2.core.physics.actor import Actor
from revolve2.core.physics.actor.urdf import to_urdf as physbot_to_urdf
from revolve2.core.physics.running import (
    ActorControl,
    ActorState,
    Batch,
    BatchResults,
    EnvironmentResults,
    EnvironmentState,
    Runner,
)

from isaacgym.terrain_utils import *
import random

class LocalRunner(Runner):
    class _Simulator:
        ENV_SIZE = 0.0

        @dataclass
        class GymEnv:
            env: gymapi.Env  # environment handle
            actors: List[
                int
            ]  # actor handles, in same order as provided by environment description

        _real_time: bool
        _env_conditions: List

        _gym: gymapi.Gym
        _batch: Batch

        _sim: gymapi.Sim
        _viewer: Optional[gymapi.Viewer]
        _simulation_time: int
        _gymenvs: List[
            GymEnv
        ]  # environments, in same order as provided by batch description

        def __init__(
            self,
            batch: Batch,
            sim_params: gymapi.SimParams,
            headless: bool,
            real_time: bool,
            env_conditions: List,
        ):
            self._gym = gymapi.acquire_gym()
            self._batch = batch
            self._env_conditions = env_conditions

            self._sim = self._create_sim(sim_params)
            self._gymenvs = self._create_envs()

            if headless:
                self._viewer = None
            else:
                self._viewer = self._create_viewer()

            self._real_time = real_time

            self._gym.prepare_sim(self._sim)

        def _create_sim(self, sim_params: gymapi.SimParams) -> gymapi.Sim:
            sim = self._gym.create_sim(type=gymapi.SIM_PHYSX, params=sim_params)

            if sim is None:
                raise RuntimeError()

            return sim

        def _create_envs(self) -> List[GymEnv]:
            gymenvs: List[LocalRunner._Simulator.GymEnv] = []

            static_friction, dynamic_friction, y_rotation_degrees, platform, playground = self._env_conditions
            y_rotation_degrees = float(y_rotation_degrees)
            static_friction = float(static_friction)
            dynamic_friction = float(dynamic_friction)

            print(static_friction, dynamic_friction, y_rotation_degrees, platform, playground)

            terrain_width = 3.
            terrain_length = 6.
            horizontal_scale = 0.25  # [m]
            vertical_scale = 0.005  # [m]
            num_rows = int(terrain_width/horizontal_scale)
            num_cols = int(terrain_length/horizontal_scale)
            heightfield = np.zeros((num_rows, num_cols), dtype=np.int16)

            def new_sub_terrain(): return SubTerrain(width=num_rows, length=num_cols, vertical_scale=vertical_scale, horizontal_scale=horizontal_scale)
            
            
            def tilted_terrain(terrain, slope=1):
                """
                Generate a sloped terrain

                Parameters:
                    terrain (SubTerrain): the terrain
                    slope (int): positive or negative slope
                Returns:
                    terrain (SubTerrain): update terrain
                """

                x = np.arange(0, terrain.width)
                y = np.arange(0, terrain.length)
                xx, yy = np.meshgrid(x, y, sparse=True)
                yy = yy.reshape(1, terrain.length)
                max_height = int(slope * (terrain.horizontal_scale / terrain.vertical_scale) * terrain.length)
                terrain.height_field_raw[np.arange(terrain.width), :] += (max_height * yy / terrain.length).astype(terrain.height_field_raw.dtype)
                return terrain

            # Rugged terrain
            if playground == "0":
                heightfield[0:num_rows, :] = random_uniform_terrain(new_sub_terrain(), min_height=-0.01, max_height=0.01, step=0.15, downsampled_scale=0.1).height_field_raw
            
            elif playground == "1":
                # Define the tilted terrain (modified from the sloped_terrain)
                
                # tilted terrain
                heightfield[0: num_rows, :] = tilted_terrain(new_sub_terrain(), slope = 0.10).height_field_raw
            
            elif playground == "3":
                def mix_sub_terrain(): return SubTerrain(width=num_rows, length=int(num_cols/6), vertical_scale=vertical_scale, horizontal_scale=horizontal_scale)

                mixing = [
                    tilted_terrain(mix_sub_terrain(), slope = 0).height_field_raw, 
                    random_uniform_terrain(mix_sub_terrain(), min_height=-0.01, max_height=0.01, step=0.15, downsampled_scale=0.1).height_field_raw,
                    tilted_terrain(mix_sub_terrain(), slope = 0.10).height_field_raw,
                    tilted_terrain(mix_sub_terrain(), slope = 0).height_field_raw, 
                    random_uniform_terrain(mix_sub_terrain(), min_height=-0.01, max_height=0.01, step=0.15, downsampled_scale=0.1).height_field_raw,
                    tilted_terrain(mix_sub_terrain(), slope = 0.10).height_field_raw,
                ]

                random.shuffle(mixing)

                heightfield[:, 0:int(num_cols/6)] = mixing[0]
                heightfield[:, int(num_cols/6): int(2*num_cols/6)] = mixing[1]
                heightfield[:, int(2*num_cols/6): int(3*num_cols/6)] = mixing[2]
                heightfield[:, int(3*num_cols/6): int(4*num_cols/6)] = mixing[3]
                heightfield[:, int(4*num_cols/6): int(5*num_cols/6)] = mixing[4]
                heightfield[:, int(5*num_cols/6):num_cols] = mixing[5]
            

            vertices, triangles = convert_heightfield_to_trimesh(heightfield, horizontal_scale=horizontal_scale, vertical_scale=vertical_scale, slope_threshold=1.5)
            tm_params = gymapi.TriangleMeshParams()
            tm_params.nb_vertices = vertices.shape[0]
            tm_params.nb_triangles = triangles.shape[0]
            tm_params.transform.p.x = -1.
            tm_params.transform.p.y = -1.
            self._gym.add_triangle_mesh(self._sim, vertices.flatten(), triangles.flatten(), tm_params)




            # TODO this is only temporary. When we switch to the new isaac sim it should be easily possible to
            # let the user create static object, rendering the group plane redundant.
            # But for now we keep it because it's easy for our first test release.
            
            #plane_params = gymapi.PlaneParams()
            
            
            # adds (possible) rotation to the y-axis
            # ps: because camera is also rotated, we see the hill raising from the center to the right of the screen
            
            #plane_params.normal = gymapi.Vec3(0.0,
            #                                  -np.sin(y_rotation_degrees*np.pi/180),
            #                                  np.cos(y_rotation_degrees*np.pi/180))
            
            #plane_params.distance = 0
            #plane_params.static_friction = static_friction
            #plane_params.dynamic_friction = dynamic_friction
            #plane_params.restitution = 0
            #self._gym.add_ground(self._sim, plane_params)

            num_per_row = int(math.sqrt(len(self._batch.environments)))

            for env_index, env_descr in enumerate(self._batch.environments):
                env = self._gym.create_env(
                    self._sim,
                    gymapi.Vec3(-self.ENV_SIZE, -self.ENV_SIZE, 0.0),
                    gymapi.Vec3(self.ENV_SIZE, self.ENV_SIZE, self.ENV_SIZE),
                    num_per_row,
                )

                gymenv = self.GymEnv(env, [])
                gymenvs.append(gymenv)


                # add platform to env
                '''
                if int(platform) == 1:
                    sizex = 6.0
                    sizey = 2.0
                    sizez = 1.0
                    platform_height_adjust = sizez/2.0
                    platform_asset = self._gym.create_box(self._sim, sizex, sizey, sizez)
                    pose = gymapi.Transform()
                    #pose.p = gymapi.Vec3(0,  0,   platform_height_adjust, )
                    pose.p = gymapi.Vec3(0,  0,   platform_height_adjust, )
                    pose.r = gymapi.Quat(0, 0, 0, 1)
                    plat1_handle = self._gym.create_actor(env, platform_asset, pose, "plat", env_index, 1)
                    pose = gymapi.Transform()
                    #pose.p = gymapi.Vec3(0, sizey, platform_height_adjust, )
                    pose.p = gymapi.Vec3(0, sizey,   platform_height_adjust, )
                    pose.r = gymapi.Quat(0, 0, 0, 1)
                    plat2_handle = self._gym.create_actor(env, platform_asset, pose, "plat2", env_index, 1)
                    self._gym.set_rigid_body_color(env, plat1_handle, 0, gymapi.MESH_VISUAL, gymapi.Vec3(0.1, 0.1, 0.1))
                    self._gym.set_rigid_body_color(env, plat2_handle, 0, gymapi.MESH_VISUAL, gymapi.Vec3(0, 1, 0))
                '''

                for actor_index, posed_actor in enumerate(env_descr.actors):
                    # sadly isaac gym can only read robot descriptions from a file,
                    # so we create a temporary file.
                    botfile = tempfile.NamedTemporaryFile(
                        mode="r+", delete=False, suffix=".urdf"
                    )
                    botfile.writelines(
                        physbot_to_urdf(
                            posed_actor.actor,
                            f"robot_{actor_index}",
                            Vector3(),
                            Quaternion(),
                        )
                    )
                    botfile.close()
                    asset_root = os.path.dirname(botfile.name)
                    urdf_file = os.path.basename(botfile.name)
                    asset_options = gymapi.AssetOptions()
                    asset_options.angular_damping = 0.0
                    actor_asset = self._gym.load_urdf(
                        self._sim, asset_root, urdf_file, asset_options
                    )
                    os.remove(botfile.name)

                    if actor_asset is None:
                        raise RuntimeError()

                    pose = gymapi.Transform()
                    pose.p = gymapi.Vec3(
                        posed_actor.position.x,
                        posed_actor.position.y,
                        posed_actor.position.z,
                    )
                    pose.r = gymapi.Quat(
                        posed_actor.orientation.x,
                        posed_actor.orientation.y,
                        posed_actor.orientation.z,
                        posed_actor.orientation.w,
                    )

                    # create an aggregate for this robot
                    # disabling self collision to both improve performance and improve stability
                    num_bodies = self._gym.get_asset_rigid_body_count(actor_asset)
                    num_shapes = self._gym.get_asset_rigid_shape_count(actor_asset)
                    enable_self_collision = False
                    self._gym.begin_aggregate(
                        env, num_bodies, num_shapes, enable_self_collision
                    )

                    actor_handle: int = self._gym.create_actor(
                        env,
                        actor_asset,
                        pose,
                        f"robot_{actor_index}",
                        env_index,
                        0,
                    )
                    self._gym.set_rigid_body_color(env, actor_handle, 0, gymapi.MESH_VISUAL, gymapi.Vec3(1, 0, 0))

                    gymenv.actors.append(actor_handle)

                    self._gym.end_aggregate(env)

                    # TODO make all this configurable.
                    props = self._gym.get_actor_dof_properties(env, actor_handle)
                    props["driveMode"].fill(gymapi.DOF_MODE_POS)
                    props["stiffness"].fill(1.0)
                    props["damping"].fill(0.05)
                    self._gym.set_actor_dof_properties(env, actor_handle, props)
                    self._gym.create_box(self._sim, 100, 100, 100)
                    all_rigid_props = self._gym.get_actor_rigid_shape_properties(
                        env, actor_handle
                    )

                    for body, rigid_props in zip(
                        posed_actor.actor.bodies,
                        all_rigid_props,
                    ):
                        rigid_props.friction = body.static_friction
                        rigid_props.rolling_friction = body.dynamic_friction

                    self._gym.set_actor_rigid_shape_properties(
                        env, actor_handle, all_rigid_props
                    )

                    self.set_actor_dof_position_targets(
                        env, actor_handle, posed_actor.actor, posed_actor.dof_states
                    )
                    self.set_actor_dof_positions(
                        env, actor_handle, posed_actor.actor, posed_actor.dof_states
                    )

            return gymenvs

        def _create_viewer(self) -> gymapi.Viewer:
            # TODO provide some sensible default and make configurable
            viewer = self._gym.create_viewer(self._sim, gymapi.CameraProperties())
            if viewer is None:
                raise RuntimeError()
            num_per_row = math.sqrt(len(self._batch.environments))

            platform = self._env_conditions[3]
            move_camzoom = 0
            move_camroty = 0
            move_camhight = 0
            if int(platform) == 1:
                move_camzoom = 0.5
                move_camroty = -2.5
                move_camhight = 2

            # TEMP adjustment of camera position
            num_per_row = num_per_row*1.7

            cam_pos = gymapi.Vec3(
                num_per_row / 2.0 + 0.5 + move_camzoom,
                num_per_row / 2.0 - 0.5 + move_camroty,
                num_per_row + move_camhight
            )
            cam_target = gymapi.Vec3(
                num_per_row / 2.0 + 0.5 - 1, num_per_row / 2.0 - 0.5, 0.0
            )
            self._gym.viewer_camera_look_at(viewer, None, cam_pos, cam_target)

            return viewer

        def run(self) -> BatchResults:
            results = BatchResults([EnvironmentResults([]) for _ in self._gymenvs])

            control_step = 1 / self._batch.control_frequency
            sample_step = 1 / self._batch.sampling_frequency

            last_control_time = 0.0
            last_sample_time = 0.0

            # sample initial state
            self._append_states(results, 0.0)

            self._gym.subscribe_viewer_keyboard_event(self._viewer, gymapi.KEY_SPACE, "space_shoot")

            # VISUAL DEBUG2: set to false if you wanna use spacebar to start sim (and possibly the step by step)
            do_physics_step = True

            while (
                time := self._gym.get_sim_time(self._sim)
            ) < self._batch.simulation_time:
                import time as _time
                # _time.sleep(1)
                # do control if it is time
                if time >= last_control_time + control_step:
                    last_control_time = math.floor(time / control_step) * control_step
                    control = ActorControl()
                    self._batch.control(control_step, control)

                    for (env_index, actor_index, targets) in control._dof_targets:
                        env_handle = self._gymenvs[env_index].env
                        actor_handle = self._gymenvs[env_index].actors[actor_index]
                        actor = (
                            self._batch.environments[env_index]
                            .actors[actor_index]
                            .actor
                        )

                        self.set_actor_dof_position_targets(
                            env_handle, actor_handle, actor, targets
                        )

                # sample state if it is time
                if time >= last_sample_time + sample_step:
                    last_sample_time = int(time / sample_step) * sample_step
                    self._append_states(results, time)

                # Check if spacebar was pressed
                for event in self._gym.query_viewer_action_events(self._viewer):
                    if event.action == "space_shoot":
                        if event.value > 0.5:
                            do_physics_step = True
                        break

                # step simulation
                if do_physics_step:
                    self._gym.simulate(self._sim)

                # VISUAL DEBUG1: uncomment this line for step by step space-based physics visualization
                #do_physics_step = False

                self._gym.fetch_results(self._sim, True)

                if self._viewer is not None:
                    self._gym.step_graphics(self._sim)
                    self._gym.draw_viewer(self._viewer, self._sim, False)

                if self._real_time:
                    self._gym.sync_frame_time(self._sim)

            # sample one final time
            self._append_states(results, time)

            return results

        def set_actor_dof_position_targets(
            self,
            env_handle: gymapi.Env,
            actor_handle: int,
            actor: Actor,
            targets: List[float],
        ) -> None:
            if len(targets) != len(actor.joints):
                raise RuntimeError("Need to set a target for every dof")

            if not all(
                [
                    target >= -joint.range and target <= joint.range
                    for target, joint in zip(
                        targets,
                        actor.joints,
                    )
                ]
            ):
                raise RuntimeError("Dof targets must lie within the joints range.")

            self._gym.set_actor_dof_position_targets(
                env_handle,
                actor_handle,
                targets,
            )

        def set_actor_dof_positions(
            self,
            env_handle: gymapi.Env,
            actor_handle: int,
            actor: Actor,
            positions: List[float],
        ) -> None:
            num_dofs = len(actor.joints)

            if len(positions) != num_dofs:
                raise RuntimeError("Need to set a position for every dof")

            if num_dofs != 0:  # isaac gym does not understand zero length arrays...
                dof_states = np.zeros(num_dofs, dtype=gymapi.DofState.dtype)
                dof_positions = dof_states["pos"]

                for i in range(len(dof_positions)):
                    dof_positions[i] = positions[i]
                self._gym.set_actor_dof_states(
                    env_handle, actor_handle, dof_states, gymapi.STATE_POS
                )

        def cleanup(self) -> None:
            if self._viewer is not None:
                self._gym.destroy_viewer(self._viewer)
            self._gym.destroy_sim(self._sim)

        def _append_states(self, batch_results: BatchResults, time: float) -> None:
            for gymenv, environment_results in zip(
                self._gymenvs, batch_results.environment_results
            ):
                env_state = EnvironmentState(time, [])
                for actor_handle in gymenv.actors:
                    pose = self._gym.get_actor_rigid_body_states(
                        gymenv.env, actor_handle, gymapi.STATE_POS
                    )["pose"]

                    position = pose["p"][0]  # [0] is center of root element
                    orientation = pose["r"][0]
                    env_state.actor_states.append(
                        ActorState(
                            Vector3([position[0], position[1], position[2]]),
                            Quaternion(
                                [
                                    orientation[0],
                                    orientation[1],
                                    orientation[2],
                                    orientation[3],
                                ]
                            ),
                        )
                    )
                environment_results.environment_states.append(env_state)

    _sim_params: gymapi.SimParams
    _headless: bool
    _real_time: bool

    def __init__(
        self,
        sim_params: gymapi.SimParams,
        env_conditions: List,
        headless: bool = False,
        real_time: bool = False,
    ):
        self._sim_params = sim_params
        self._headless = headless
        self._real_time = real_time
        self._env_conditions = env_conditions

    @staticmethod
    def SimParams() -> gymapi.SimParams:
        sim_params = gymapi.SimParams()
        sim_params.dt = 0.02
        sim_params.substeps = 2
        sim_params.up_axis = gymapi.UP_AXIS_Z
        # TODO: get values from config
        sim_params.gravity = gymapi.Vec3(0.0, 0.0, -9.81)

        sim_params.physx.solver_type = 1
        sim_params.physx.num_position_iterations = 4
        sim_params.physx.num_velocity_iterations = 1
        sim_params.physx.num_threads = 1
        sim_params.physx.use_gpu = True

        # increase if memory errors persist
        max_gpu_contact_pairs_boast = 20
        sim_params.physx.max_gpu_contact_pairs = sim_params.physx.max_gpu_contact_pairs * max_gpu_contact_pairs_boast

        return sim_params

    async def run_batch(self, batch: Batch) -> BatchResults:
        print(
            "\n--- Begin Isaac Gym log ----------------------------------------------------------------------------"
        )

        # sadly we must run Isaac Gym in a subprocess, because it has some big memory leaks.
        result_queue: mp.Queue = mp.Queue()  # type: ignore # TODO
        process = mp.Process(
            target=self._run_batch_impl,

            args=(
                result_queue,
                batch,
                self._sim_params,
                self._headless,
                self._real_time,
                self._env_conditions,
            ),
        )
        process.start()
        environment_results = []
        # environment_results are sent seperately for every environment
        # because sending all at once is too big for the queue.
        # should be good enough for now.
        # if the program hangs here in the future,
        # improve the way the results are passed back to the parent program.
        while (environment_result := result_queue.get()) is not None:
            environment_results.append(environment_result)
        process.join()
        print(
            colored.attr("reset")
            + "--- End Isaac Gym log ------------------------------------------------------------------------------\n"
        )
        return BatchResults(environment_results)

    @classmethod
    def _run_batch_impl(
        cls,
        result_queue: mp.Queue,  # type: ignore # TODO
        batch: Batch,
        sim_params: gymapi.SimParams,
        headless: bool,
        real_time: bool,
        env_conditions: List,
    ) -> None:
        _Simulator = cls._Simulator(batch, sim_params, headless, real_time, env_conditions)
        batch_results = _Simulator.run()
        _Simulator.cleanup()
        for environment_results in batch_results.environment_results:
            result_queue.put(environment_results)
        result_queue.put(None)
