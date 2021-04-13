import math
from math import floor

import http_framework.interfaceUtils
import http_framework.worldLoader
import src.my_utils
import src.movement
import src.pathfinding
import src.scheme_utils
import src.agent
import numpy as np
from random import choice, random
from scipy.interpolate import interp1d
import src.linedrawing
import src.manipulation
import names

class State:

    agent_heads = []
    tallest_building_height = 30
    changed_blocks = {}
    blocks = []  # 3D Array of all the assets in the state
    trees = []
    saplings = []
    water = []  # tile positions
    world_y = 0
    world_x = 0
    world_z = 0
    len_x = 0
    len_y = 0
    len_z = 0
    unwalkable_blocks = ['minecraft:water', 'minecraft:lava']
    agent_height = 2
    agent_jump_ability = 1
    heightmap_offset = -1
    node_size = 3
    road_nodes = []
    roads = []
    road_segs = set()
    construction = set()  # nodes where buildings can be placed
    lots = set()

    build_minimum_phase_1 = 2
    build_minimum_phase_2 = 30
    build_minimum_phase_3 = 50


    ## Create surface grid
    def __init__(self, world_slice=None, blocks_file=None, max_y_offset=tallest_building_height):
        if not world_slice is None:
            self.rect = world_slice.rect
            self.world_slice = world_slice
            self.blocks, self.world_y, self.len_y, self.abs_ground_hm = self.gen_blocks_array(world_slice)
            self.rel_ground_hm = self.gen_rel_ground_hm(self.abs_ground_hm)  # a heightmap based on the state's y values. -1
            self.static_ground_hm = np.copy(self.rel_ground_hm)  # use this for placing roads
            self.heightmaps = world_slice.heightmaps
            self.built = set()
            self.types = self.gen_types(self.rel_ground_hm)  # 2D array. Exclude leaves because it would be hard to determine tree positions
            self.world_x = world_slice.rect[0]
            self.world_z = world_slice.rect[1]
            self.len_x = world_slice.rect[2] - world_slice.rect[0]
            self.len_z = world_slice.rect[3] - world_slice.rect[1]
            self.end_x = world_slice.rect[2]
            self.end_z = world_slice.rect[3]
            self.legal_actions = src.movement.gen_all_legal_actions(
                self.blocks, vertical_ability=self.agent_jump_ability, heightmap=self.rel_ground_hm,
                actor_height=self.agent_height, unwalkable_blocks=["minecraft:water", 'minecraft:lava']
            )
            self.pathfinder = src.pathfinding.Pathfinding()
            self.sectors = self.pathfinder.create_sectors(self.heightmaps["MOTION_BLOCKING_NO_LEAVES"],
                                            self.legal_actions)  # add tihs into State
            self.nodes, self.node_pointers = self.gen_nodes(self.len_x, self.len_z, self.node_size)
            self.prosperity = np.zeros((self.len_x, self.len_z))
            self.traffic = np.zeros((self.len_x, self.len_z))
            self.updateFlags = np.zeros((self.len_x, self.len_z))
            self.built_heightmap = {}
            self.exterior_heightmap = {}
            self.generated_building = False
            self.changed_blocks_xz = set()
            self.total_changed_blocks = {}
            self.total_changed_blocks_xz = set()
            self.phase = 1
            self.bends = 0
            self.semibends = 0
            self.bendcount = 0
            self.agents = dict()  # holds agent and position
            self.new_agents = set()  # agents that were just created
            # print(self.types)
            # print(self.nodes[self.node_pointers[(5,5)]].get_type())
            # print('nodes is '+str(len(self.nodes)))
            # print('traffic is '+str(len(self.traffic)))

            for water in self.water:
                # src.states.set_state_block(self, water[0], self.rel_ground_hm[water[0]][water[1]], water[1], 'minecraft:iron_block')
                pass


        else:  # for testing
            print("State instantiated for testing!")
            def parse_blocks_file(file_name):
                size, blocks = src.scheme_utils.get_schematic_parts(file_name)
                dx, dy, dz = size
                blocks3D = [[[0 for z in range(dz)] for y in range(dy)] for x in range(dx)]
                for x in range(dx):
                    for y in range(dy):
                        for z in range(dz):
                            index = y*(dz)*(dx) + z*(dx) + x
                            inv_y = dy - 1 - y
                            blocks3D[x][inv_y][z] = "minecraft:"+blocks[index]
                return dx, dy, dz, blocks3D
            self.len_x, self.len_y, self.len_z, self.blocks = parse_blocks_file(blocks_file)


    def place_building_at(self, ctrn_node, bld, bld_lenx, bld_lenz, wood_type):
        # check if theres adequate space by getting nodes, and move the building to center it if theres extra space
        # if not ctrn_node in self.construction: return
        # for every orientation of this node+neighbors whose lenx and lenz are the min space required to place building at
        min_nodes_in_x = math.ceil(bld_lenx/ctrn_node.size)
        min_nodes_in_z = math.ceil(bld_lenz/ctrn_node.size)
        min_tiles = min_nodes_in_x*min_nodes_in_z
        found_ctrn_dir = None
        found_nodes = set()

        # get rotation based on neighboring road
        found_road = None
        face_dir = None
        for dir in src.movement.cardinals:  # maybe make this cardinal only
            nx = ctrn_node.center[0] + dir[0]*ctrn_node.size
            nz = ctrn_node.center[1] + dir[1]*ctrn_node.size
            if self.out_of_bounds_Node(nx, nz): continue
            np = (nx, nz)
            neighbor = self.nodes[self.node_pointers[np]]
            if neighbor in self.roads:
                found_road = neighbor
                face_dir = dir
                break
        if found_road == None:
            return False
        rot = 0
        if face_dir[0] == 1: rot = 2
        if face_dir[0] == -1: rot = 0
        if face_dir[1] == -1: rot = 1
        if face_dir[1] == 1: rot = 3
        # print('face_dir is '+str(face_dir))
        # self.set_block(ctrn_node.center[0], 17, ctrn_node.center[1],"minecraft:emerald_block")
        if rot in [1,3]:
            temp = min_nodes_in_x
            min_nodes_in_x = min_nodes_in_z
            min_nodes_in_z = temp
        ## find site where x and z are reversed. this rotates
        for dir in src.movement.diagonals:
            if found_ctrn_dir != None:
                break
            tiles = 0
            for x in range(0, min_nodes_in_x):
                for z in range(0, min_nodes_in_z):
                    # x1 = ctrn_node.center[0]+x*ctrn_node.size*dir[0]
                    # z1 = ctrn_node.center[1]+z*ctrn_node.size*dir[1]
                    nx = ctrn_node.center[0]+x*ctrn_node.size*dir[0]
                    nz = ctrn_node.center[1]+z*ctrn_node.size*dir[1]
                    if self.out_of_bounds_Node(nx, nz): break
                    node = self.nodes[(nx,nz)]
                    if not node in self.construction: break
                    if node in self.roads: break  # don't go over roads
                    tiles += 1
                    found_nodes.add(node)
            if tiles == min_tiles:  # found a spot!
                found_ctrn_dir = dir
                break
            else:
                found_nodes.clear()
        if found_ctrn_dir == None:  # if there's not enough space, return
            return False

        ctrn_dir = found_ctrn_dir
        x1 = ctrn_node.center[0] - ctrn_dir[0]  # to uncenter
        z1 = ctrn_node.center[1] - ctrn_dir[1]
        x2 = ctrn_node.center[0] + ctrn_dir[0] + ctrn_dir[0] * ctrn_node.size * (min_nodes_in_x - 1)
        z2 = ctrn_node.center[1] + ctrn_dir[1] + ctrn_dir[1] * ctrn_node.size * (min_nodes_in_z - 1)
        xf = min(x1, x2)  # since the building is placed is ascending
        zf = min(z1, z2)
        y = self.rel_ground_hm[xf][zf] # temp
        status, building_heightmap, exterior_heightmap = src.scheme_utils.place_schematic_in_state(self, bld, xf, y, zf, rot=rot, built_arr=self.built, wood_type=wood_type)
        if status == False:
            return False
        self.built_heightmap.update(building_heightmap)
        self.exterior_heightmap.update(exterior_heightmap)
        # build road from the road to the building
        self.create_road(found_road.center, ctrn_node.center, road_type="None", points=None, leave_lot=False, add_as_road_type=False)
        xmid = int((x2 + x1)/2)
        zmid = int((z2 + z1)/2)
        distmax = math.dist((ctrn_node.center[0]-ctrn_dir[0], ctrn_node.center[1]-ctrn_dir[1]), (xmid, zmid))
        # build construction site ground
        for n in found_nodes:
            # for each of the nodes' tiles, generate random, based on dist. Also, add it to built.
            for dir in src.movement.idirections:
                x = n.center[0] + dir[0]
                z = n.center[1] + dir[1]
                # add to built
                y = int(self.rel_ground_hm[x][z]) - 1
                inv_chance = math.dist((x, z), (xmid, zmid))/distmax  # clamp to 0-1
                if inv_chance == 1.0: # stylistic choice: don't let corners be placed
                    continue
                attenuate = 0.8
                if random() > inv_chance*attenuate:
                    block = choice(src.my_utils.ROAD_SETS['default'])
                    self.set_block(x, y, z, block)
        y = self.rel_ground_hm[xf][zf] + 5
        # self.set_block(xf, y, zf, "minecraft:diamond_block")
        # debug
        for n in found_nodes:
            x = n.center[0]
            z = n.center[1]
            y = self.rel_ground_hm[x][z] + 9
            # self.set_block(x, y, z, "minecraft:iron_block")
        ## remove nodes from construction
        for node in list(found_nodes):
            self.construction.remove(node)
            self.built.add(node)
        self.generated_building = True
        return True


    def get_nearest_tree(self,x,z):
        return src.movement.find_nearest(x,z,self.trees, 5, 30, 10)


    # note: not every block has a node. These will point to None
    def gen_nodes(self, len_x, len_z, node_size):
        if len_x < 0 or len_z < 0:
            print("Lengths cannot be <0")
        node_size = 3  # in assets
        nodes_in_x = int(len_x / node_size)
        nodes_in_z = int(len_z / node_size)
        node_count = nodes_in_x * nodes_in_z
        self.last_node_pointer_x = nodes_in_x * node_size - 1  # TODO verify the -1
        self.last_node_pointer_z = nodes_in_z * node_size - 1
        nodes = {}  # contains coord pointing to data struct
        node_pointers = np.full((len_x,len_z), None)
        for x in range(nodes_in_x):
            for z in range(nodes_in_z):
                cx = x*node_size+1
                cz = z*node_size+1
                node = self.Node(self, center=(cx, cz), types=[src.my_utils.TYPE.BROWN.name], size=self.node_size)  # TODO change type
                nodes[(cx, cz)] = node
                node_pointers[cx][cz] = (cx, cz)
                for dir in src.movement.directions:
                    nx = cx + dir[0]
                    nz = cz + dir[1]
                    node_pointers[nx][nz] = (cx, cz)
        for node in nodes.values():
            node.adjacent = node.gen_adjacent(nodes, node_pointers, self)
            node.neighbors = node.gen_neighbors(nodes, node_pointers, self)
            # node = node.gen_local()
            node.local = node.gen_local(nodes, node_pointers, self)
            node.range, node.water_resources, node.resource_neighbors = node.gen_range(nodes, node_pointers, self)
        return nodes, node_pointers




    class Node:

        local = set()
        def __init__(self, state, center, types, size):
            self.center = center
            self.size = size
            # self.local_prosperity = 0  # sum of all of its assets
            self.mask_type = set()
            self.mask_type.update(types)
            self.neighbors = set()
            self.lot = None
            self.range = set()
            self.adjacent = set()
            self.locality_radius = 3
            self.range_radius = 4
            self.neighborhood_radius = 1
            self.adjacent_radius = 1
            self.state = state
            # self.type = set()  # to cache type()

        def get_tiles(self):
            tiles = []
            radius = math.floor(self.size / 2)
            for x in range(-radius, radius + 1):
                for z in range(-radius, radius + 1):
                    nx = self.center[0] + x
                    nz = self.center[1] + z
                    tiles.append((nx,nz))
            return tiles


        # the tiles' types + mask_type (like building or roads
        def get_type(self):
            if self in self.state.built:
                self.add_mask_type(src.my_utils.TYPE.BUILT.name)
            all_types = set()
            for tile_pos in self.get_tiles():
                tx, tz = tile_pos
                if self.state.out_of_bounds_Node(tx, tz): continue
                all_types.add(self.state.types[tx][tz])  # each block has a single type
            for t in self.mask_type:
                all_types.add(t)
            self.type = all_types
            return all_types


        def add_prosperity(self, amt):
            self.state.prosperity[self.center[0]][self.center[1]] += amt
            self.state.updateFlags[self.center[0]][self.center[1]] = 1


        def prosperity(self):
            return self.state.prosperity[self.center[0]][self.center[1]]


        def traffic(self):
            if not self.state.out_of_bounds_Node(self.center[0], self.center[1]):  # let's get rid of this check later
                return self.state.traffic[self.center[0]][self.center[1]]


        def add_mask_type(self, type):
            self.mask_type.add(type)


        def clear_type(self, state):
            if self in state.construction:
                state.construction.discard(self)
            self.mask_type.clear()


        def gen_adjacent(self, nodes, node_pointers, state):
            adj = set()
            for dir in src.movement.directions:
                pos = (self.center[0] + dir[0]*self.size, self.center[1] + dir[1]*self.size)
                if state.out_of_bounds_Node(*pos): continue
                node = nodes[node_pointers[pos]]
                adj.add(node)
            return adj


        def add_neighbor(self, node):
            self.neighbors.add(node)


        def gen_neighbors(self, nodes, node_pointers, state):
            neighbors = set()
            i = 0
            for r in range(1, self.neighborhood_radius+1):
                for ox in range(-r, r+1):
                    for oz in range(-r, r+1):
                        if ox == 0 and oz == 0: continue
                        x = (self.center[0])+ox*self.size
                        z = (self.center[1])+oz*self.size
                        if state.out_of_bounds_Node(x, z):
                            continue
                        node = nodes[node_pointers[(x, z)]]
                        neighbors.add(node)
            return neighbors


        # get local nodes
        def gen_local(self, nodes, node_pointers, state):
            local = set()
            i = 0
            for r in range(1, self.locality_radius + 1):
                for ox in range(-r, r + 1):
                    for oz in range(-r, r + 1):
                        # if ox == 0 and oz == 0: continue
                        x = (self.center[0]) + ox * self.size
                        z = (self.center[1]) + oz * self.size
                        if state.out_of_bounds_Node(x, z):
                            continue
                        node = nodes[node_pointers[(x, z)]]
                        if src.my_utils.TYPE.WATER.name in node.get_type():
                            continue
                        local.add(node)
            return local


        def gen_range(self, nodes, node_pointers, state):
            local = set([self])
            water_neighbors = []
            resource_neighbors = []
            for r in range(1, self.range_radius + 1):
                for ox in range(-r, r + 1):
                    for oz in range(-r, r + 1):
                        if ox == 0 and oz == 0: continue
                        x = (self.center[0]) + ox * self.size
                        z = (self.center[1]) + oz * self.size
                        if state.out_of_bounds_Node(x, z):
                            continue
                        node = nodes[node_pointers[(x, z)]]
                        if src.my_utils.TYPE.WATER.name in node.get_type():
                            continue
                        if src.my_utils.TYPE.WATER.name in node.type:
                            water_neighbors.append(node)
                        if src.my_utils.TYPE.TREE.name in node.type \
                                or src.my_utils.TYPE.GREEN.name in node.type \
                                or src.my_utils.TYPE.CONSTRUCTION.name in node.type:
                                resource_neighbors.append(node)
                        local.add(node)
            self.built_resources = self.prosperity
            return local, water_neighbors, resource_neighbors


        def get_locals_positions(self):
            arr = []
            for node in self.local:
                arr.append(node.center)
            return arr


        def get_neighbors_positions(self):
            arr = []
            for node in self.neighbors:
                arr.append(node.center)
            return arr


        def get_ranges_positions(self):
            arr = []
            for node in self.range:
                arr.append(node.center)
            return arr


        def get_lot(self):
            # finds enclosed green areas
            lot = set([self])
            new_neighbors = set()
            for i in range(5):
                new_neighbors = set([e for n in lot for e in n.adjacent if e not in lot and (
                        src.my_utils.TYPE.GREEN.name in e.mask_type or src.my_utils.TYPE.TREE.name in e.mask_type or src.my_utils.TYPE.CONSTRUCTION.name in e.mask_type)])
                accept = set([n for n in new_neighbors if src.my_utils.TYPE.CONSTRUCTION.name not in n.mask_type])
                if len(new_neighbors) == 0:
                    break
                lot.update(accept)
            if len([n for n in new_neighbors if src.my_utils.TYPE.CONSTRUCTION.name not in n.mask_type]) == 0:  # neighbors except self
                return lot
            else:
                return None

    # def calc_local_prosperity(self, node_center):
    #     x = node_center[0]
    #     z = node_center[1]
    #     local_p = self.prosperity[x][z]
    #     for dir in src.movement.directions:
    #         local_p += self.prosperity[x + dir[0]][z + dir[1]]
    #     return local_p


    def gen_heightmaps(self, world_slice):
        result = {}
        for name, heightmap in world_slice.heightmaps.items():
            result[name] = []
            for x in range(len(heightmap)):
                result[name].append([])
                for z in range(len(heightmap[0])):
                    state_adjusted_y = heightmap[x][z]# + self.heightmap_offset
                    result[name][x].append(state_adjusted_y)
        return result


    def gen_blocks_array(self, world_slice, max_y_offset=tallest_building_height):
        x1, z1, x2, z2 = world_slice.rect
        abs_ground_hm = world_slice.get_heightmap("MOTION_BLOCKING_NO_LEAVES", -1) # inclusive of ground
        def get_y_bounds(_heightmap):  ## Get the y range that we'll save tha state in?
            lowest = _heightmap[0][0]
            highest = _heightmap[0][0]
            for col in _heightmap:
                for block_y in col:
                    if (block_y < lowest):
                        lowest = block_y
                    elif (block_y > highest):
                        highest = block_y
            return lowest, highest
        y1, y2  = get_y_bounds(abs_ground_hm)  # keep range not too large
        y2 += max_y_offset
        if (y2 > 150):
            print("warning: Y bound is really high!")

        len_z = abs(z2 - z1)
        len_y = abs(y2 - y1)
        len_x = abs(x2 - x1)
        blocks = [[[0 for z in range(len_z)] for y in range(len_y)] for x in range(len_x)] # the format of the state isn't the same as the file's.
        xi = 0
        yi = 0
        zi = 0
        for x in range(x1, x2):
            yi = 0
            for y in range(y1, y2):
                zi = 0
                for z in range(z1, z2):
                    block = world_slice.getBlockAt((x, y, z))
                    blocks[xi][yi][zi] = block
                    zi += 1
                yi += 1
            xi += 1
        world_y = y1
        len_y = y2 - y1
        return blocks, world_y, len_y, abs_ground_hm


    def gen_rel_ground_hm(self, abs_ground_hm):
        result = []
        for x in range(len(abs_ground_hm)):
            result.append([])
            for z in range(len(abs_ground_hm[0])):
                state_adjusted_y = int(abs_ground_hm[x][z]) - self.world_y + 1#+ self.heightmap_offset
                result[x].append(state_adjusted_y)
        return result


    def update_node_type(self, x, z):
        prev_type = self.types[x][z]
        new_type = self.determine_type(x, z)
        if prev_type == "TREE":
            if new_type != "TREE":
                self.trees.remove((x, z))
        #     y = self.heightmaps["MOTION_BLOCKING_NO_LEAVES"][x][z]-self.world_y+self.heightmap_offset
        #     if self.is_log(x, y, z):
        #         new_type = "TREE"
        self.types[x][z] = new_type

    def update_heightmaps(self):
        for x in range(len(self.abs_ground_hm)):
            for z in range(len(self.abs_ground_hm[0])):
                if (x,z) in self.built_heightmap: # ignore buildings
                    y = self.built_heightmap[(x,z)] - 1
                    self.abs_ground_hm[x][z] = y + self.world_y
                    self.rel_ground_hm[x][z] = y + 1
                elif (x,z) in self.exterior_heightmap:
                    y = self.exterior_heightmap[(x,z)] - 1
                    self.abs_ground_hm[x][z] = y + self.world_y
                    self.rel_ground_hm[x][z] = y + 1
                else:  # traverse down to find first non passable block
                    y = self.traverse_down_till_block(x, z) + 1
                    self.abs_ground_hm[x][z] = y + self.world_y - 1
                    self.rel_ground_hm[x][z] = y
                curr_height = self.rel_ground_hm[x][z]
                if self.static_ground_hm[x][z] > curr_height:  # don't reduce heightmap ever. this is to avoid bugs rn
                    self.static_ground_hm[x][z] = curr_height
        return


    def traverse_down_till_block(self,x,z):
        y = len(self.blocks[0])-1  # start from top
        while y > 0:
            block = self.blocks[x][y][z]
            if block not in src.my_utils.TYPE_TILES.tile_sets[src.my_utils.TYPE.PASSTHROUGH.value]:
                # print("traversed till "+block)
                break
            y-=1
        return y


    def gen_types(self, heightmap):
        xlen = len(self.blocks)
        zlen = len(self.blocks[0][0])
        types = [["str" for i in range(zlen)] for j in range(xlen)]
        for x in range(xlen):
            for z in range(zlen):
                type = self.determine_type(x, z, heightmap)
                if type == "TREE":
                    self.trees.append((x, z))
                if type == "WATER":
                    self.water.append((x,z))
                types[x][z] = type  # each block is a list of types. The node needs to chek its assets
        print("done initializing types")
        return types


    def determine_type(self, x, z, heightmap, yoffset = 0):
        block_y = int(heightmap[x][z]) - 1 + yoffset
        block = self.blocks[x][block_y][z]
        for i in range(1, len(src.my_utils.TYPE) + 1):
            if block in src.my_utils.TYPE_TILES.tile_sets[i]:
                return src.my_utils.TYPE(i).name
        return src.my_utils.TYPE.BROWN.name



    def save_state(self, state, file_name):
        f = open(file_name, 'w')
        len_x = len(state.blocks)
        len_y = len(state.blocks[0])
        len_z = len(state.blocks[0][0])
        f.write('{}, {}, {}, {}\n'.format(len_x, state.world_y, len_y, len_z))
        i = 0
        for position,block in self.changed_blocks.items():
            to_write = position+';'+block+"\n"
            f.write(to_write)
            i += 1
        f.close()
        print(str(i)+" assets saved")


    def load_state(self, save_file):
        f = open(save_file, "r")
        lines = f.readlines()
        size = lines[0]
        blocks = lines[1:]
        n_blocks = len(blocks)
        i = 0
        for line in blocks:
            position_raw, block = line.split(';')
            state_x, state_y, state_z = src.my_utils.convert_key_to_coords(position_raw)
            http_framework.interfaceUtils.placeBlockBatched(
                self.world_x + state_x, self.world_y + state_y, self.world_z + state_z, block, n_blocks
            )
            i += 1
        f.close()
        self.changed_blocks.clear()
        print(str(i)+" assets loaded")


    # NOTE: you need to get heihtmaps after you place block info. they should be last
    def step(self, is_rendering=True,use_total_changed_blocks=False):
        i = 0
        changed_arr = self.changed_blocks
        changed_arr_xz = self.changed_blocks_xz
        if use_total_changed_blocks:
            changed_arr = self.total_changed_blocks
            changed_arr_xz = self.total_changed_blocks_xz
        n_blocks = len(changed_arr)
        self.old_legal_actions = self.legal_actions.copy()  # needed to update
        for position, block in changed_arr.items():
            x,y,z = position
            if is_rendering == True:
                http_framework.interfaceUtils.placeBlockBatched(self.world_x + x, self.world_y + y, self.world_z + z, block, n_blocks)
            # http_framwork.interfaceUtils.setBlock(self.world_x + state_x, self.world_y + state_y, self.world_z + state_z, block)
            i += 1
        self.update_heightmaps()  # must wait until all assets are placed
        for position in changed_arr_xz:
            x,z = position
            self.update_block_info(x, z)  # Must occur after new assets have been placed. Also, only the surface should run it.
        changed_arr.clear()
        changed_arr_xz.clear()
        if i > 0:
            print(str(i)+" assets rendered")


    ## do we wanna cache tree locations? I don't want them to cut down buildings lol


    # is this state x
    def update_block_info(self, x, z):  # this might be expensive if you use this repeatedly in a group
        for xo in range(-1, 2):
            for zo in range(-1, 2):
                bx = x + xo
                bz = z + zo
                if self.out_of_bounds_2D(bx, bz):
                    continue
                self.legal_actions[bx][bz] = src.movement.get_legal_actions_from_block(self.blocks, bx, bz, self.agent_jump_ability,
                                                                                   self.rel_ground_hm, self.agent_height,
                                                                                   self.unwalkable_blocks)

        # if x z not in closed_for_propagation
        self.pathfinder.update_sector_for_block(x, z, self.sectors,
                                                sector_sizes=self.pathfinder.sector_sizes,
                                                legal_actions=self.legal_actions, old_legal_actions=self.old_legal_actions)


    def get_adjacent_block(self, x_origin, y_origin, z_origin, x_off, y_off, z_off):
        x_target = x_origin + x_off
        y_target = y_origin + y_off
        z_target = z_origin + z_off
        if self.out_of_bounds_3D(x_target, y_target, z_target):
            return None
        return self.blocks[x_target][y_target][z_target]


    def get_all_adjacent_blocks(self, x_origin, y_origin, z_origin):
        adj_blocks = []
        for x_off in range(-1, 2):
            for y_off in range(-1, 2):
                for z_off in range(-1, 2):
                    if x_off == 0 and y_off == 0 and z_off == 0:
                        continue
                    block = self.get_adjacent_block(x_origin, y_origin, z_origin, x_off, y_off, z_off)
                    if block is None:
                        continue
                    adj_blocks.append((block, x_origin+x_off, y_origin+y_off, z_origin+z_off))
        return adj_blocks


    def world_to_state(self,coords):
        x = coords[0] - self.world_x
        z = coords[2] - self.world_z
        y = self.rel_ground_hm[x][z]
        result = (x,y,z)
        return result


    def out_of_bounds_3D(self, x, y, z):
        return True if \
            x >= len(self.blocks) \
            or y >= len(self.blocks[0]) \
            or z >= len(self.blocks[0][0]) \
            or x < 0 \
            or y < 0 \
            or z < 0 \
            else False


    def out_of_bounds_2D(self, x, z):
        return True if x < 0 or z < 0 or x >= len(self.blocks) or z >= len(self.blocks[0][0]) \
            else False

    def out_of_bounds_Node(self, x, z):
        # if x < 0 or z < 0 or x > self.last_node_pointer_x or z > self.last_node_pointer_z: # the problem is that some assets don't point to a tile.
        if x < 0 or z < 0 or x > self.last_node_pointer_x or z > self.last_node_pointer_z: # the problem is that some assets don't point to a tile.
            return True
        return False


    def set_block(self, x, y, z, block_name):
        self.blocks[x][y][z] = block_name
        key = src.my_utils.convert_coords_to_key(x, y, z)
        self.changed_blocks[key] = block_name


    def set_type_building(self, nodes):
        for node in nodes:
            if not node in self.built:
                if src.my_utils.TYPE.GREEN.name in node.get_type() or \
                        src.my_utils.TYPE.BROWN.name in node.type or \
                        src.my_utils.TYPE.TREE.name in node.type:
                    node.clear_type(self)
                    node.add_mask_type(src.my_utils.TYPE.CONSTRUCTION.name)
                    self.construction.add(node)


    def set_type_road(self, node_points, road_type):
        for point in node_points:
            node = self.nodes[self.node_pointers[point]]
            if src.my_utils.TYPE.WATER.name in node.get_type():
                node.clear_type(self)
                node.add_mask_type(src.my_utils.TYPE.BRIDGE.name) # we don't use add_type. instead we give each tile a type
            else:
                node.clear_type(self)
                node.add_mask_type(road_type)
            for road in self.roads:
                # node.clear_type(self)  # mine
                node.add_neighbor(road)
                road.add_neighbor(node)
            if node in self.construction:
                self.construction.discard(node)
            self.roads.append(node)  # put node in roads array


    def init_main_st(self):
        (x1, y1) = choice(self.water)
        n_pos = self.node_pointers[(x1, y1)]
        water_checks = 100
        i = 0
        while n_pos == None:
            if i > water_checks:
                print("Error: could not find suitable water source!")
                return
            (x1, y1) = choice(self.water)
            n_pos = self.node_pointers[(x1, y1)]
            i+=1
        n = self.nodes[n_pos]
        n1_options = list(set(n.range) - set(n.local))  # Don't put water right next to water, depending on range
        n1 = np.random.choice(n1_options, replace=False)  # Pick random point of the above
        while src.my_utils.TYPE.WATER.name in n1.mask_type:  # generate and test until n1 isn't water
            n1 = np.random.choice(n1_options, replace=False)  # If it's water, choose again
        n2_options = list(set(n1.range) - set(n1.local))  # the length of the main road is the difference between the local and the range
        n2 = np.random.choice(n2_options, replace=False)  # n2 is based off of n1's range, - local to make it farther
        points = src.linedrawing.get_line((n1.center[0], n1.center[1]), (n2.center[0], n2.center[1]))
        water_found = True
        limit = 10
        i = 0
        while water_found:
            if i > limit:
                return False
            water_found = False
            for p in points:
                x = self.node_pointers[p][0]
                z = self.node_pointers[p][1]
                y = self.rel_ground_hm[x][z] - 1
                b = self.blocks[x][y][z]
                if b in src.my_utils.TYPE_TILES.tile_sets[src.my_utils.TYPE.WATER.value]:
                    n2 = np.random.choice(n2_options, replace=False)
                    points = src.linedrawing.get_line((n1.center[0], n1.center[1]), (n2.center[0], n2.center[1]))
                    water_found = True
                    i+=1
                    break
        points = self.points_to_nodes(points)  # points is the path of nodes from the chosen
        (x1, y1) = points[0]
        (x2, y2) = points[len(points) - 1]
        self.set_type_road(points, src.my_utils.TYPE.MAJOR_ROAD.name) # TODO check if the fact that this leads to repeats causes issue
        middle_nodes = []
        if len(points) > 2:
            middle_nodes = points[1:len(points) - 1]
        self.road_segs.add(
            RoadSegment(self.nodes[(x1,y1)], self.nodes[(x2,y2)], middle_nodes, src.my_utils.TYPE.MAJOR_ROAD.name, self.road_segs, self))
        for (x, y) in points:
            # adjacent = self.nodes[(x,y)].adjacent
            # adjacent = self.nodes[(x,y)].local  # this is where we increase building range
            adjacent = self.nodes[(x,y)].range  # this is where we increase building range
            adjacent = [s for n in adjacent for s in n.adjacent]  # every node in the road builds buildings around them
            for pt in adjacent:
                if pt not in points:
                    self.set_type_building([self.nodes[(pt.center[0], pt.center[1])]])
        p1 = (x1, y1)
        p2 = (x2, y2)
        self.init_lots(*p1, *p2)  # main street is a lot
        self.create_road(node_pos1=p1, node_pos2=p2, road_type=src.my_utils.TYPE.MAJOR_ROAD.name)

        # add starter agents
        for agent_pos in [p1, p2]:
            print(str(agent_pos))
            head = choice(State.agent_heads)
            new_agent = src.agent.Agent(self, *agent_pos, walkable_heightmap=self.rel_ground_hm,
                                        name=names.get_first_name(), head=head)
            self.add_agent(new_agent)
        return True


    def add_agent(self, agent, use_auto_motive=True):
        self.new_agents.add(agent)  # to be handled by update_agents
        agent.set_motive(agent.Motive.LOGGING)


    def init_lots(self, x1, y1, x2, y2):
        (mx, my) = (int(x1 + x2) // 2, int(y1 + y2) // 2)  # middle
        self.add_lot([(mx - 25, my - 25), (mx + 25, my + 25)])


    def add_lot(self, points):
        lot = Lot(self, points)
        if lot is not None:
            self.lots.add(lot)
            return True
        return False


    def points_to_nodes(self, points):
        nodes = []
        for point in points:
            node = self.node_pointers[point]  # node coords
            if node not in nodes:
                nodes.append(node)
        return nodes

    # might have to get point2 within the func, rather than pass it in
    def create_road(self, node_pos1, node_pos2, road_type, points=None, leave_lot=False, correction=5, road_blocks=None, inner_block_rate=1.0, outer_block_rate=0.75, fringe_rate=0.05, add_as_road_type = True, bend_if_needed=False):
        self.road_nodes.append(self.nodes[self.node_pointers[node_pos1]])
        self.road_nodes.append(self.nodes[self.node_pointers[node_pos2]])
        block_path = []
        if points == None:
            block_path = src.linedrawing.get_line(node_pos1, node_pos2) # inclusive




            # if bend_if_needed:
            #     closed = set()
            #     for i in range(len(block_path)):
            #         if (block_path[i] in self.built):
            #             built_node = block_path[i]
            #             ## try to get a bent road from that
            #             # first find a diagonal that is not in built and isn't type water
            #             for diag in src.movement.diagonals:
            #                 nx = self.node_size * diag[0] + built_node.center[0]
            #                 nz = self.node_size * diag[1] + built_node.center[1]
            #                 if (nx, nz) in closed: continue
            #                 if self.out_of_bounds_node(nx, nz): continue
            #                 closed.add((nx, nz))
            #                 p1_to_diag = src.linedrawing.get_line(node_pos1, (nx,nz))
            #                 if any(tile in self.built for tile in p1_to_diag): continue
            #                 # p2_to_diag = src.linedrawing.get_line((nx, nz), node_pos2)
            #                 closest_point, p2_to_diag = self.get_closest_point(node=self.nodes[(nx, nz)],
            #                                                                     lots=[],
            #                                                                     possible_targets=self.roads,
            #                                                                     road_type=road_type,
            #                                                                     state=self,
            #                                                                     leave_lot=false,
            #                                                                     correction=correction)
            #                 if any(tile in self.built for tile in p2_to_diag): continue
            #                 block_path = p1_to_diag + p2_to_diag
            #                 self.bends+=1
        else:
            block_path = points
        if bend_if_needed:
            tile_coords = [tilepos for node in self.built for tilepos in node.get_tiles()]
            if any(tile in tile_coords for tile in block_path):
                # get nearest built
                built_node_coords = [node.center for node in self.built]  # returns building node coords
                built_diags = [(node[0] + dir[0] * self.node_size, node[1] + dir[1] * self.node_size)
                               # returns diagonals to building nodes
                               for node in built_node_coords for dir in src.movement.diagonals if (
                               node[0] + dir[0] * self.node_size,
                               node[1] + dir[1] * self.node_size) not in self.built]
                nearest_builts = src.movement.find_nearest(*node_pos1, built_diags, 5, 30, 10)
                # print("nearest builts is ")
                # print(str(nearest_builts))
                # self.bendcount += len(near)
                closed = set()
                found_bend = False
                for built in nearest_builts:
                    if found_bend == True: break
                    for diag in src.movement.diagonals:
                        nx = self.node_size * diag[0] + built[0]
                        nz = self.node_size * diag[1] + built[1]
                        if (nx, nz) in closed: continue
                        closed.add((nx, nz))
                        if self.out_of_bounds_Node(nx, nz): continue
                        p1_to_diag = src.linedrawing.get_line(node_pos1, (nx, nz))
                        if any(tile in tile_coords for tile in p1_to_diag): continue

                        # # debug
                        # for tile in p1_to_diag:
                        #     set_state_block(self,tile[0], self.rel_ground_hm[tile[0]][tile[1]]+10,tile[1], 'minecraft:diamond_block')

                        self.semibends += 1
                        # p2_to_diag = src.linedrawing.get_line((nx, nz), node_pos2)
                        closest_point, p2_to_diag = self.get_closest_point(node=self.nodes[(nx, nz)],
                                                                           lots=[],
                                                                           possible_targets=self.roads,
                                                                           road_type=road_type,
                                                                           state=self,
                                                                           leave_lot=False,
                                                                           correction=correction)
                        if p2_to_diag is None: continue  # if none found, try again
                        if any(tile in tile_coords for tile in
                               p2_to_diag): continue  # if building is in path. try again

                        # # debug
                        for tile in p1_to_diag:
                            set_state_block(self, tile[0], self.rel_ground_hm[tile[0]][tile[1]] + 10, tile[1],
                                            'minecraft:diamond_block')
                        for tile in p2_to_diag:
                            set_state_block(self, tile[0], self.rel_ground_hm[tile[0]][tile[1]] + 10, tile[1],
                                            'minecraft:emerald_block')

                        block_path = p1_to_diag + p2_to_diag  # concat two, building-free roads
                        self.bends += 1
                        found_bend = True
                        break
        # add road segnmets
        middle_nodes = []
        node_path = []
        if len(block_path) > 0:
            start = self.node_pointers[block_path[0]]
            node_path.append(start) # start
            for n in range(1, len(block_path)-1):
                node = self.node_pointers[block_path[n]]
                if not node in self.road_segs and node != None:
                    middle_nodes.append(node)
                    node_path.append(node)
            a = self.node_pointers
            end = self.node_pointers[block_path[len(block_path)-1]]
            node_path.append(end)  # end

        ## draw two more lines



        check1 = True
        check2 = True
        if check1:
            n1 = self.nodes[node_pos1]
            for rs in self.road_segs:
                if node_pos1 in rs.nodes:  # if the road is in roads already, split it off
                    rs.split(n1, self.road_segs, self.road_nodes, state=self)  # split RoadSegment
                    break
        if check2:
            n2 = self.nodes[node_pos2]
            for rs in self.road_segs:
                if node_pos2 in rs.nodes:
                    rs.split(n2, self.road_segs, self.road_nodes, state=self)
                    break

        # do checks
        if add_as_road_type == True:  # allows us to ignore the small paths from roads to buildings
            road_segment = RoadSegment(self.nodes[node_pos1], self.nodes[node_pos2], middle_nodes, road_type, self.road_segs, state=self)
            self.road_segs.add(road_segment)

        # place assets. TODO prolly not right- i think you wanna render road segments
        if road_blocks == None:
            road_blocks = src.my_utils.ROAD_SETS['default']
        ## render
        for block in block_path:
            x = block[0]
            z = block[1]
            y = int(self.static_ground_hm[x][z]) - 1
            if self.blocks[x][y][z] == "minecraft:water" or src.manipulation.is_log(self, x, y, z):
                continue
            if random() < inner_block_rate:
                road_block = choice(road_blocks)
                set_state_block(self, x, y, z, road_block)

        aux_path = []
        for card in src.movement.cardinals:
            # offset1 = choice(src.movement.cardinals)
            def clamp_to_state_coords(x, z):
                if x > self.last_node_pointer_x:
                    x = self.last_node_pointer_x
                elif x < 0:
                    x = 0
                if z > self.last_node_pointer_z:
                    z = self.last_node_pointer_z
                elif z < 0:
                    z = 0
                return (x,z)
            p1 = clamp_to_state_coords(block_path[0][0] + card[0], block_path[0][1] + card[1])
            p2 = clamp_to_state_coords(block_path[len(block_path)-1][0] + card[0], block_path[len(block_path)-1][1] + card[1])
            # aux1 = src.linedrawing.get_line( p1, p2 )
            aux1 = [(block[0]+card[0], block[1]+card[1]) for block in block_path]
            aux_path.extend(aux1)


        ## borders
        for block in aux_path:
            x = block[0]
            z = block[1]
            y = int(self.static_ground_hm[x][z]) - 1
            block = self.blocks[x][y][z]
            if self.blocks[x][y][z] == "minecraft:water" or src.manipulation.is_log(self, x, y, z):
                continue
            if random() < outer_block_rate:
                road_block = choice(road_blocks)
                set_state_block(self, x, y, z, road_block)

        # self.set_type_road(node_path, src.my_utils.TYPE.MAJOR_ROAD.name)
        if add_as_road_type:
            self.set_type_road(node_path, road_type)
        return [node_pos1, node_pos2]


    # def init_main_st(self, water_pts):
    #     (x1, y1) = random.choice(water_pts)  # start in water
    #     n = self.array[x1][y1]
    #     n1_options = list(set(n.range()) - set(n.local()))
    #     n1 = np.random.choice(n1_options, replace=False)
    #     while Type.WATER in n1.type:  # generate and test until n1 isn't water
    #         n1 = np.random.choice(n1_options, replace=False)
    #     n2_options = list(set(n1.range()) - set(n1.local()))
    #     n2 = np.random.choice(n2_options, replace=False)
    #     points = get_line((n1.x, n1.y), (n2.x, n2.y))
    #     while any(Type.WATER in self.array[x][y].type for (x, y) in
    #               points):  # if any of the points of the potential road are in water, regenerate
    #         n2 = np.random.choice(n2_options, replace=False)
    #         points = get_line((n1.x, n1.y), (n2.x, n2.y))
    #
    #     (x1, y1) = points[0]
    #     (x2, y2) = points[len(points) - 1]
    #     self.set_type_road(points, Type.MAJOR_ROAD)
    #     middle_nodes = []
    #     if len(points) > 2:
    #         middle_nodes = points[1:len(points) - 1]
    #     self.roadsegments.add(
    #         RoadSegment(self.array[x1][y1], self.array[x2][y2], middle_nodes, Type.MAJOR_ROAD, self.roadsegments))
    #     for (x, y) in points:
    #         adjacent = self.array[x][y].adjacent
    #         adjacent = [s for n in adjacent for s in n.adjacent]  # every node in the road builds buildings around them
    #         for pt in adjacent:
    #             if pt not in points:
    #                 self.set_type_building([self.array[pt.x][pt.y]])
    #     self.init_lots(x1, y1, x2, y2)  # main street is a lot


    def append_road(self, point, road_type, leave_lot=False, correction=5, bend_if_needed = False):
        # convert point to node
        point = self.node_pointers[point]
        node = self.nodes[point]
        # self.roads.append((point1))
        closest_point, path_points = self.get_closest_point(node=self.nodes[self.node_pointers[point]], # get closest point to any road
                                                              lots=[],
                                                              possible_targets=self.roads,
                                                              road_type=road_type,
                                                              state=self,
                                                              leave_lot=False,
                                                              correction=correction)
        if closest_point == None:
            return
        (x2, y2) = closest_point
        closest_point = None
        if road_type == src.my_utils.TYPE.MINOR_ROAD.name:
            closest_point = self.get_point_to_close_gap_minor(*point, path_points)  # connects 2nd end of minor roads to the nearest major or minor road. I think it's a single point
        elif road_type == src.my_utils.TYPE.MAJOR_ROAD.name:  # extend major
            closest_point = self.get_point_to_close_gap_major(node, *point, path_points)  # "extends a major road to the edge of a lot"

        if closest_point is not None:
            point = closest_point
            path_points.extend(src.linedrawing.get_line((x2, y2), point))  # append to the points list the same thing in reverse? or is this a diff line?

        self.create_road(point, (x2, y2), road_type=road_type, points=path_points, bend_if_needed=bend_if_needed)


    def get_point_to_close_gap_minor(self, x1, z1, points):
        print("BUILDING MINOR ROAD")
        (x_, z_) = points[1]
        x = x1 - x_
        z = z1 - z_
        (x2, z2) = (x1 + x, z1 + z)
        while True:
            if x2 >= self.last_node_pointer_x or z2 >= self.last_node_pointer_z or x2 < 0 or z2 < 0:
                break
            landtype = self.nodes[self.node_pointers[(x2, z2)]].get_type()
            if src.my_utils.TYPE.GREEN.name in landtype or src.my_utils.TYPE.TREE.name in landtype or src.my_utils.TYPE.WATER.name in landtype:
                break
            if src.my_utils.TYPE.MAJOR_ROAD.name in landtype or src.my_utils.TYPE.MINOR_ROAD.name in landtype and src.my_utils.TYPE.BYPASS.name not in landtype:
                return (x2, z2)
            (x2, z2) = (x2 + x, z2 + z)
        return None


    def get_point_to_close_gap_major(self, node, x1, z1, points):
        print("EXTENDING MAJOR ROAD")
        # extends a major road to the edge of a lot
        if node.lot is None:
            return None
        (x_, z_) = points[1]
        x = x1 - x_
        z = z1 - z_
        (x2, z2) = (x1 + x, z1 + z)
        border = node.lot.border
        while True:
            if x2 >= self.last_node_pointer_x or z2 >= self.last_node_pointer_z or x2 < 0 or z2 < 0:
                break
            landtype = self.nodes[self.node_pointers[(x2, z2)]].get_type()
            if src.my_utils.TYPE.WATER.name in landtype:
                break
            if (x2, z2) in border:
                # landtype = self.nodes[(x2, z2)].mask_type
                return (x2, z2)
            (x2, z2) = (x2 + x, z2 + z)
        return None


    def get_closest_point(self, node, lots, possible_targets, road_type, state, leave_lot, correction=5):
        x, z = node.center
        nodes = possible_targets
        nodes = [n for n in nodes if src.my_utils.TYPE.BRIDGE.name not in n.get_type()]  # expensive
        if len(nodes) == 0:
            print("leave_lot = {} no road segments".format(leave_lot))
            return None, None
        dists = [math.hypot(n.center[0] - x, n.center[1] - z) for n in nodes]
        node2 = nodes[dists.index(min(dists))]
        (x2, z2) = (node2.center[0], node2.center[1])
        xthr = 2   # TODO tweak these
        zthr = 2
        if node.lot is None:
            if road_type is not src.my_utils.TYPE.MINOR_ROAD.name and abs(x2 - x) > xthr and abs(
                    z2 - z) > zthr:
                if node2.lot is not None:
                    (cx2, cy2) = node2.lot.center
                    (x, z) = (x + x - cx2, z + z - cy2)
                    # clamp road endpoints
                    print("BUILDING ROAD. IS IT LONG?")
                    if x >= self.last_node_pointer_x:
                        x = self.last_node_pointer_x
                    if x < 0:
                        x = 0
                    if z >= self.last_node_pointer_z:
                        z = self.last_node_pointer_z
                    if z < 0:
                        z = 0
                if abs(x2 - x) > xthr and abs(z2 - z) > zthr:
                    if not state.add_lot([(x2, z2), (x, z)]):
                        print("leave_lot = {} add lot failed".format(leave_lot))
                        return None, None
            else:
                print("Failed!")
                return None, None
        points = src.linedrawing.get_line((x, z), (node2.center[0], node2.center[1]))
        if len(points) <= 2:
            return None, None
        if not leave_lot:
            for (i, j) in points:
                if src.my_utils.TYPE.WATER.name in self.nodes[self.node_pointers[(i, j)]].mask_type:
                    return None, None
        closest_point = (node2.center[0], node2.center[1])
        return closest_point, points


    def apply_local_prosperity(self, x, z, value):
        self.prosperity[x][z] += value


def set_state_block(state, x, y, z, block_name):
    state.blocks[x][y][z] = block_name
    state.changed_blocks_xz.add((x,z))
    state.total_changed_blocks_xz.add((x,z))
    state.changed_blocks[(x,y,z)] = block_name
    state.total_changed_blocks[(x,y,z)] = block_name


class RoadSegment:
    def __init__(self, rnode1, rnode2, nodes, type, rslist, state):
        self.start = rnode1
        self.end = rnode2
        self.type = type
        self.shape = []
        self.nodes = nodes
        # mine
        # for n in nodes:
        #     if n in state.built:
        #         state.built.discard(n)
        # if self.start in state.built:
        #     state.built.discard(self.start)
        # if self.end in state.built:
        #     state.built.discard(self.end)

    def merge(self, rs2, match, rs_list, roadnodes):
        if self.type != rs2.mask_type:
            return
        if self.start == match:
            self.shape.reverse()
            self.start = self.end
        self.shape.append((match.x, match.y))
        self.nodes.append((match.x, match.y))
        if rs2.end == match:
            rs2.shape.reverse()
            rs2.end = rs2.start
        self.shape.extend(rs2.shape)
        self.nodes.extend(rs2.nodes)
        self.end = rs2.end
        rs_list.discard(rs2)
        roadnodes.remove(match)
        roadnodes.remove(match)


    def split(self, node, rs_list, roadnodes, state):
        roadnodes.append(node)
        roadnodes.append(node)

        i = 0
        while i < len(self.nodes) - 1:
            if self.nodes[i] == (node.center[0], node.center[1]):
                break
            i += 1
        nodes1 = self.nodes[:i]
        nodes2 = self.nodes[i + 1:]

        new_rs = RoadSegment(node, self.end, nodes2, self.type, roadnodes, state=state)
        rs_list.add(new_rs)

        self.nodes = nodes1
        self.end = node

        # for n in roadnodes:
        #     if n in state.built:
        #         state.built.discard(n)
        # if self.start in state.built:
        #     state.built.discard(self.start)
        # if self.end in state.built:
        #     state.built.discard(self.end)


class Lot:
    def __init__(self, state, points):
        self.state = state
        # self.neighbors = set() # neighbor lots, not currently used
        self.get_lot(points)

    def get_pt_avg(self, points):
        x = sum(x for (x, y) in points) / len(points)
        y = sum(y for (x, y) in points) / len(points)
        return (x, y)

    def get_lot(self, points):
        [pt1, pt2] = points

        (ax, ay) = self.get_pt_avg(points)
        bx, by  = (int(ax), int(ay))
        self.center = (cx, cy) = self.state.node_pointers[(bx, by)]
        center_node = self.state.nodes[(cx,cy)]

        lot = set([center_node])
        self.border = set()
        while True:
            neighbors = set([e for n in lot for e in n.adjacent if \
                             e not in lot and e.lot is None and e.center[0] != pt1[0] and e.center[0] != pt2[0] and e.center[1] != pt1[ 1] and e.center[1] != pt2[1] \
                             and src.my_utils.TYPE.WATER.name not in e.mask_type])
            if len(neighbors) > 0:
                lot.update(neighbors)
                self.border = neighbors
            else:
                break

        for node in lot:
            node.lot = self
        self.nodes = lot


    def get_nodes(self):
        return self.nodes


