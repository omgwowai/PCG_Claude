"""Bindings that make the Python graphs reproduce the official ones exactly.

Each role is one actor of L_CitySamplePCG_Demo that a Get_ActorDataByRef node reads; the role
names come from the reading nodes' titles (2026-10-13 T3D scan of the 18 graphs). ROLE_LABELS
is what Task 8 verified each path to be in the demo level; the town binds the same labels.
"""
DEMO = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo.L_CitySamplePCG_Demo:PersistentLevel."

ROLES = {
    "Terrain": DEMO + "PCGVolume_UAID_387C7649839438DB02_2022633615",
    "MainTower": DEMO + "PCGVolume_UAID_387C7649839439DB02_1290570802",
    "CentralParkFootprint": DEMO + "1_CentralPark_Footprint_2gania7pfoeg2_UAID_387C764983945CDF02_1296577182",
    "Districts": DEMO + "PCGVolume_UAID_387C7649839438DB02_2022637616",
    "Roads": DEMO + "PCGVolume_UAID_387C76498394DCE702_1944600151",
    "Highways": DEMO + "PCGVolume_UAID_387C7649839447DC02_1377087312",
    "Lots": DEMO + "PCGVolume_UAID_387C7649839438DB02_2022641618",
    "Buildings": DEMO + "PCGVolume_UAID_387C7649839438DB02_2022648621",
    "Parkings": DEMO + "PCGVolume_UAID_387C76498394A5DF02_1886871024",
    "ParkingFootprint": DEMO + "PCGVolume_UAID_387C7649839438DB02_2022646620",
    "LandmarkPark": DEMO + "Spline_UAID_387C76498394B3DF02_1392886487",
    "HighwaySpline2": DEMO + "Spline_UAID_387C76498394C5DE02_1195736599",
    "HighwaySpline3": DEMO + "Spline_UAID_387C76498394C5DE02_1470179601",
}

# Measured 2026-10-15 (pyg_probe_plan_api2.py): role -> actor label in L_CitySamplePCG_Demo. The town
# (a template copy) carries the same labels. Note ParkingFootprint is the LeftOverLots volume: Parkings
# reads the lot LeftOverLots set aside.
ROLE_LABELS = {"Terrain": "PCG_1_1_Terrain", "MainTower": "PCG_2_1_MainTower_Footprint",
               "CentralParkFootprint": "PCG_2_2_CentralPark_Footprint", "Districts": "PCG_3_1_1_Districts",
               "Roads": "PCG_3_1_2_Roads", "Highways": "PCG_3_1_3_Highways", "Lots": "PCG_3_1_4_Lots",
               "Buildings": "PCG_3_3_1_Buildings", "Parkings": "PCG_3_2_3_Parkings",
               "ParkingFootprint": "PCG_3_2_2_LeftOverLots", "LandmarkPark": "MainTowerPark",
               "HighwaySpline2": "HighWay_2", "HighwaySpline3": "HighWay_3"}

KNOBS = {}
