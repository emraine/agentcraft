### returns a tuple of coordinates, with the lower x and z values first
from enum import Enum
import http_framework.interfaceUtils
import src.agent

# https://stackoverflow.com/questions/34470597/is-there-a-dedicated-way-to-get-the-number-of-items-in-a-python-enum

ROAD_SETS = {
	'default': ["minecraft:gravel", "minecraft:granite", "minecraft:coarse_dirt", "minecraft:grass_path"]
}

STRUCTURES = {
	"med_house": [
		"med_house_1_flex",
		"med_house_2_flex",
		"med_house_3_flex",
		"med_house_4_flex",
	],
    "all": [
		"med_house_1_flex",
		"med_house_2_flex",
		"med_house_4_flex",
        "small_house_1_flex",
		"small_house_2_flex",
        "market_stall_1_flex",
		"market_stall_2_flex",
	]
}

ROTATION_LOOKUP = {
	(0, 1): "0",
	(-1, 1): "45",
	(-1, 0): "90",
	(-1, -1): "135",
	(0, -1): "180",
	(1, -1): "225",
	(1, 0): "270",
	(1, 1): "315",
}

ACTION_ITEMS = { "LOGGING": ["iron_axe"] }


class ACTION_PROSPERITY():
	LOGGING = 10


class TYPE(Enum):
	WATER = 1
	TREE = 2
	GREEN = 3
	BROWN = 4
	BUILDING = 5
	MAJOR_ROAD = 6
	MINOR_ROAD = 7
	BRIDGE = 8
	CITY_GARDEN = 9
	HIGHWAY = 10
	AIR = 11


class HEIGHTMAPS(Enum):
	MOTION_BLOCKING = 1
	MOTION_BLOCKING_NO_LEAVES = 2
	OCEAN_FLOOR = 3
	WORLD_SURFACE = 4

class TYPE_TILES:
	tile_sets = {
		TYPE.WATER.value: {  #WATER
			"minecraft:water",
            "minecraft:lily_pad"
		},
		TYPE.TREE.value: {  # FOREST
			"minecraft:log",
			"minecraft:dark_oak_log",
			"minecraft:stripped_dark_oak_log",
			"minecraft:spruce_log",
			"minecraft:acacia_log",
			"minecraft:stripped_spruce_log",
			"minecraft:oak_log",
			"minecraft:stripped_oak_log",
			"minecraft:jungle_log",
			"minecraft:stripped_jungle_log",
            "minecraft:stripped_acacia_log",
            "minecraft:stripped_birch_log",
			"minecraft:birch_log",
		},
		TYPE.GREEN.value: {  # GREEN
			"minecraft:grass_block",
			"minecraft:sand"
			"minecraft:coarse_dirt",
			"minecraft:dirt",
			"minecraft:oak_sapling",
		},
		TYPE.BROWN.value: {  # BROWN
			"minecraft:gravel",
			"minecraft:diorite",
			"minecraft:stone",
		},
		TYPE.BUILDING.value: {  # BUILDING
			""
		},
		TYPE.MAJOR_ROAD.value: {  # MAJOR ROAD

		},
		TYPE.MINOR_ROAD.value: {  # MINOR ROAD

		},
		TYPE.BRIDGE.value: {  # BRIDGE

		},
		TYPE.CITY_GARDEN.value: {

		},
		TYPE.HIGHWAY.value: {

		},
		TYPE.AIR.value: {
			"minecraft:air",
			"minecraft:cave_air"
		}
	}


def correct_area(area):
    if area[0] > area[2]:
        swap_array_elements(area, 0, 2)
    if area[1] > area[3]:
        swap_array_elements(area, 1, 3)
    return (area[0], area[1], area[2], area[3])


def swap_array_elements(arr, a, b):
    temp = arr[a]
    arr[a] = arr[b]
    arr[b] = temp


def convert_coords_to_key(x, y, z):
    # return str(x)+','+str(y)+','+str(z)
	return (x, y, z)


def convert_key_to_coords(key):
	# x, y, z = [int(coord) for coord in key.split(',')]
	# return x, y, z
    return key


# copy paste the text when you run /data get block, from {SkullOwner onwards
def get_player_head_block_id(name, SkullOwnerSet, rotation="1"):
	prop = SkullOwnerSet[1:]
	prop = prop.split(", x")[0]
	prop = prop.replace(" ", "")
	command = """player_head[rotation={0}]{{display:{{Name:"{{\\"text\\":\\"{1}\\"}}"}},{2}}}"""\
		.format(rotation, name, prop)
	return command



