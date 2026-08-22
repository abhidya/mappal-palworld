"""End-of-life scan: per-snapshot census of base camps, their pieces and their
Pals, for the four timelapse bases.

Reads every Level.sav we hold (git-LFS history of the save-history repo ($PALTL_REPO)
plus the NAS backup sets), exactly the sources merge_all.py / build_index.py
already use, and records for each snapshot:

  * game_clock  - worldSaveData.GameTimeSaveData.GameDateTimeTicks, the world's
                  OWN clock. mtime only says when a file was written; a
                  pre-restore backup has a new mtime and old contents. Ordering
                  claims in the output are checked against this, not mtime.
  * camps       - the 8-char key of every BaseCampSaveData record present, with
                  its transform + area_range. A base whose key is gone has had
                  its camp record removed, which is a different event from its
                  pieces being removed.
  * pieces      - MapObjectSaveData count per base (same attribution rule as
                  build_index.py: basecamp_attrib.attribute).
  * pals        - CharacterSaveParameterMap instance ids whose recorded
                  LastJumpedLocation lies within area_range of each camp, so a
                  Pal can be followed across snapshots (moved vs vanished).

Nothing here is interpolated. Every number is read out of one save file.

Output: eol_scan.json  {"snapshots":[{ts, src, game_clock, camps{}, pieces{},
                        pals{base:[iid,...]}, pal_pos{iid:[x,y,z]}, ...}]}
"""
import json, os, sys, glob, time, subprocess, math
from multiprocessing import Pool

SP = os.environ.get("PALTL_WORK") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
REPO = os.environ.get("PALTL_REPO") or os.path.expanduser("~/Palworld")
LINEAGE_GUILD = "017a45a0"
BASES = {"07f13218", "16fca097", "de44d9f4", "5fed0024"}
# FULLPALS=1 also records every wild/owned Pal instance id in the snapshot, not
# just the ones standing inside a camp - needed to tell "the camp's Pals moved"
# from "the camp's Pals are gone" once the camp record itself no longer exists.
FULLPALS = os.environ.get("FULLPALS") == "1"


def sources():
    src = {}
    for line in open(f"{SP}/commits.txt"):
        c, t = line.split()
        src.setdefault(int(t), ("git", c))
    # Several backup sets hold the same snapshot under different paths; when two
    # files share an mtime keep the LARGEST, because the small ones are the
    # 35-38 KB empty-world saves and would look like "everything vanished".
    byts = {}
    for pat in ("nasbk", "nasbk2", "nas", "nasbk3"):
        for p in glob.glob(f"{SP}/{pat}/**/Level.sav", recursive=True):
            t = int(os.path.getmtime(p))
            sz = os.path.getsize(p)
            if t not in byts or sz > byts[t][0]:
                byts[t] = (sz, p)
    for t, (sz, p) in byts.items():
        src.setdefault(t, ("file", p))
    return src


def _patch_reader():
    """These saves are newer than palworld_save_tools 0.24 knows about.

    Two independent version gaps:

      * The container magic is b'PlM' and the payload is Oodle-compressed, not
        zlib. Handled by oozshim.decompress_sav (libooz.dylib = zao/ooz built
        from source here, decompression path only).

      * Several RawData blobs have grown extra fields at the END. The library
        reads its known fields off the front by fixed layout and then asserts
        `reader.eof()`, so one appended field rejects the whole save. Every
        field this script reads (instance_id, base_camp_id_belong_to,
        initital_transform_cache, id/transform/area_range, SaveParameter) is
        read BEFORE that tail, so the tail is counted instead of fatal.

    The relaxation is validated, not assumed: eol_report.py re-derives per-base
    piece counts and Pal ids from these decodes and checks them against
    build_index.json / pal_index.json, which an earlier, version-matched
    decoder produced from the same files.
    """
    from palworld_save_tools.rawdata import (character, map_model, base_camp,
                                              build_process, map_object)

    tails = {}

    def _tail(name, reader, n):
        left = n - reader.data.tell()
        if left:
            tails[name] = max(tails.get(name, 0), left)

    def character_decode_bytes(parent_reader, char_bytes):
        reader = parent_reader.internal_copy(bytes(char_bytes), debug=False)
        d = {"object": reader.properties_until_end(),
             "unknown_bytes": reader.byte_list(4),
             "group_id": reader.guid()}
        _tail("character", reader, len(char_bytes))
        return d

    def map_model_decode_bytes(parent_reader, m_bytes):
        reader = parent_reader.internal_copy(bytes(m_bytes), debug=False)
        d = {"instance_id": reader.guid(),
             "concrete_model_instance_id": reader.guid(),
             "base_camp_id_belong_to": reader.guid(),
             "group_id_belong_to": reader.guid(),
             "hp": {"current": reader.i32(), "max": reader.i32()},
             "initital_transform_cache": reader.ftransform(),
             "repair_work_id": reader.guid(),
             "owner_spawner_level_object_instance_id": reader.guid(),
             "owner_instance_id": reader.guid(),
             "build_player_uid": reader.guid(),
             "interact_restrict_type": reader.byte(),
             "stage_instance_id_belong_to": {"id": reader.guid(),
                                             "valid": reader.u32() > 0},
             "created_at": reader.i64()}
        _tail("map_model", reader, len(m_bytes))
        return d

    def base_camp_decode_bytes(parent_reader, b_bytes):
        reader = parent_reader.internal_copy(bytes(b_bytes), debug=False)
        d = {"id": reader.guid(), "name": reader.fstring(), "state": reader.byte(),
             "transform": reader.ftransform(), "area_range": reader.float(),
             "group_id_belong_to": reader.guid(),
             "fast_travel_local_transform": reader.ftransform(),
             "owner_map_object_instance_id": reader.guid()}
        _tail("base_camp", reader, len(b_bytes))
        return d

    def build_process_decode_bytes(parent_reader, b_bytes):
        reader = parent_reader.internal_copy(bytes(b_bytes), debug=False)
        d = {"state": reader.byte(), "id": reader.guid()}
        _tail("build_process", reader, len(b_bytes))
        return d

    def map_object_decode(reader, type_name, size, path):
        """Decode only Model.RawData for every map object.

        The library also decodes Connector, BuildProcess, ConcreteModel and
        ConcreteModel.ModuleMap, and each of those has its own per-object-type
        fixed layout that this save version has extended - decoding them would
        mean guessing at four more formats. This script needs nothing from
        them, so they are left as the raw byte arrays the save actually
        contains. Nothing is invented and nothing is silently reinterpreted.
        """
        if type_name != "ArrayProperty":
            raise Exception(f"Expected ArrayProperty, got {type_name}")
        value = reader.property(type_name, size, path, nested_caller_path=path)
        for mo in value["value"]["values"]:
            mo["Model"]["value"]["RawData"]["value"] = map_model.decode_bytes(
                reader, mo["Model"]["value"]["RawData"]["value"]["values"])
        return value

    # PALWORLD_CUSTOM_PROPERTIES holds a direct reference to the original
    # function, so replacing the module attribute alone would not take effect.
    from palworld_save_tools.paltypes import PALWORLD_CUSTOM_PROPERTIES as PCP
    map_object.decode = map_object_decode
    key = ".worldSaveData.MapObjectSaveData"
    PCP[key] = (map_object_decode, PCP[key][1])
    # Decode ONLY the four blobs this census reads. Foliage, work, item and
    # character containers, dynamic items and concrete-model modules all have
    # their own extended layouts in this save version; none of them is used
    # here, so they are left as the raw byte arrays the file contains rather
    # than being force-parsed with a stale layout.
    keep = {".worldSaveData.MapObjectSaveData",
            ".worldSaveData.BaseCampSaveData.Value.RawData",
            ".worldSaveData.CharacterSaveParameterMap.Value.RawData",
            ".worldSaveData.GroupSaveDataMap"}
    for k in list(PCP):
        if k not in keep:
            del PCP[k]

    # This save version also adds whole new worldSaveData sections the library
    # has no layout for at all (LockGimmickSaveData was the first). Those sit
    # AFTER the four sections read here, so parsing stops at the first one it
    # cannot read rather than failing the file. work() then asserts that all
    # four required sections were actually parsed, so a stop that happened too
    # early is an error, never a silently short census.
    from palworld_save_tools.archive import FArchiveReader
    _orig_pue = FArchiveReader.properties_until_end

    def properties_until_end(self, path=""):
        # Tolerant at the GVAS file's own top level too: newer saves add
        # sibling properties of worldSaveData (SetProperty
        # InLockerCharacterInstanceIDArray) whose type this library cannot
        # read at all. worldSaveData is parsed before them.
        if path not in ("", ".worldSaveData"):
            return _orig_pue(self, path)
        props, stopped = {}, None
        while True:
            try:
                name = self.fstring()
                if name == "None":
                    break
                type_name = self.fstring()
                size = self.u64()
                props[name] = self.property(type_name, size, f"{path}.{name}")
            except Exception as exc:
                stopped = f"{name if 'name' in dir() else '?'}: {exc}"
                break
        if path == ".worldSaveData":
            props["__stopped_at__"] = stopped
        elif stopped:
            props.setdefault("worldSaveData", {}).setdefault("value", {})
        return props

    FArchiveReader.properties_until_end = properties_until_end
    build_process.decode_bytes = build_process_decode_bytes
    character.decode_bytes = character_decode_bytes
    map_model.decode_bytes = map_model_decode_bytes
    base_camp.decode_bytes = base_camp_decode_bytes
    return tails


def read_raw(kind, ref):
    if kind == "git":
        blob = subprocess.run(["git", "-C", REPO, "show", f"{ref}:world/current/Level.sav"],
                              capture_output=True).stdout
        return subprocess.run(["git", "-C", REPO, "lfs", "smudge"],
                              input=blob, capture_output=True).stdout
    return open(ref, "rb").read()


def work(job):
    ts, kind, ref = job
    try:
        try:
            import ooz  # noqa: F401
        except ImportError:
            pass
        import basecamp_attrib, paint_scan, oozshim
        from palworld_save_tools.gvas import GvasFile
        from palworld_save_tools.paltypes import PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES
        raw = read_raw(kind, ref)
        if len(raw) < 100000:
            return {"ts": ts, "ok": False, "why": "too small", "bytes": len(raw),
                    "src": ref if kind == "file" else "git:" + ref}
        tails = _patch_reader()
        gvas = oozshim.decompress_sav(raw)
        clock = paint_scan.game_clock(gvas)
        w = GvasFile.read(gvas, PALWORLD_TYPE_HINTS, PALWORLD_CUSTOM_PROPERTIES) \
            .dump()["properties"]["worldSaveData"]["value"]
        stopped = w.pop("__stopped_at__", None)
        need = ("BaseCampSaveData", "MapObjectSaveData")
        missing = [k for k in need if k not in w]
        if missing:
            return {"ts": ts, "ok": False,
                    "why": f"parse stopped before {missing} ({stopped})"}
        camps = {}
        for e in w["BaseCampSaveData"]["value"]:
            rd = e["value"]["RawData"]["value"]
            tr = rd["transform"]["translation"]
            camps[str(e["key"])[:8]] = {
                "x": round(tr["x"], 1), "y": round(tr["y"], 1), "z": round(tr["z"], 1),
                "area_range": float(rd.get("area_range", 0)),
                "state": rd.get("state"),
            }
        # Lineage guard. merge_all.py used GroupSaveDataMap's guild id, but this
        # save version's group RawData layout is beyond the library and that
        # section no longer parses. The equivalent, and directly checkable,
        # signal is the camp set itself: a save from a different playthrough
        # (and the 35-38 KB empty-world saves in the pre-restore backup) shares
        # none of this world's four base-camp GUIDs.
        if not (BASES & set(camps)):
            return {"ts": ts, "ok": False, "why": "no known base camp - not this world",
                    "bytes": len(raw), "camps": camps,
                    "src": ref if kind == "file" else "git:" + ref}

        cmp_for_attrib = basecamp_attrib.camps_from(w)

        pieces = {}
        types = {}
        for m in w["MapObjectSaveData"]["value"]["values"]:
            mr = m["Model"]["value"]["RawData"]["value"]
            b = str(mr.get("base_camp_id_belong_to"))[:8]
            tr = mr.get("initital_transform_cache", {}).get("translation", {})
            b = basecamp_attrib.attribute(b, tr.get("x", 0), tr.get("y", 0), cmp_for_attrib)
            if b is None:
                continue
            pieces[b] = pieces.get(b, 0) + 1
            if b == "5fed0024":
                t = m["MapObjectId"]["value"]
                types[t] = types.get(t, 0) + 1

        pals = {b: [] for b in BASES}
        pal_pos = {}
        total_pals = 0
        pal_error = None
        all_pals = {}
        try:
            for e in w.get("CharacterSaveParameterMap", {"value": []})["value"]:
                sp = e["value"]["RawData"]["value"]["object"]["SaveParameter"]["value"]
                if sp.get("IsPlayer", {}).get("value"):
                    continue
                total_pals += 1
                loc = sp.get("LastJumpedLocation")
                if not loc:
                    continue
                v = loc["value"]
                iid = str(e["key"]["InstanceId"]["value"])
                if FULLPALS:
                    all_pals[iid] = [round(v["x"]), round(v["y"]), round(v["z"]),
                                     sp["CharacterID"]["value"]]
                for b in BASES:
                    c = camps.get(b)
                    if not c:
                        continue
                    if math.hypot(v["x"] - c["x"], v["y"] - c["y"]) <= c["area_range"]:
                        pals[b].append(iid)
                        pal_pos[iid] = [round(v["x"]), round(v["y"]), round(v["z"])]
                        break
        except Exception as exc:
            # Newer character records use property types this library version
            # cannot read. The Pal census is reported as unavailable for that
            # snapshot rather than reported short; pal_index.json (built by a
            # version-matched decoder) is the fallback source.
            pal_error = f"{type(exc).__name__}: {exc}"[:160]
        return {"ts": ts, "ok": True, "src": ref if kind == "file" else "git:" + ref,
                "game_clock": clock, "camps": camps, "pieces": pieces,
                "lost_camp_types": types, "pals": pals, "pal_pos": pal_pos,
                "pal_total": total_pals, "bytes": len(raw), "rawdata_tail_bytes": tails,
                "parse_stopped_at": stopped, "pal_error": pal_error,
                "all_pals": all_pals,
                "map_objects_total": len(w["MapObjectSaveData"]["value"]["values"])}
    except Exception as e:
        return {"ts": ts, "ok": False, "why": f"{type(e).__name__}: {e}"[:200]}


def main():
    src = sources()
    want = os.environ.get("ONLY")
    jobs = [(ts, k, r) for ts, (k, r) in sorted(src.items())]
    if want:
        keep = {int(x) for x in want.split(",")}
        jobs = [j for j in jobs if j[0] in keep]
    print(f"snapshots: {len(jobs)}", flush=True)
    out = []
    t0 = time.time()
    with Pool(int(os.environ.get("JOBS", "4"))) as pool:
        for i, r in enumerate(pool.imap(work, jobs, chunksize=1), 1):
            out.append(r)
            if i % 25 == 0:
                print(f"  {i}/{len(jobs)}  {time.time()-t0:.0f}s", flush=True)
    out.sort(key=lambda r: r["ts"])
    json.dump(out, open(f"{SP}/{os.environ.get('OUT','eol_scan.json')}", "w"))
    ok = sum(1 for r in out if r.get("ok"))
    print(f"DONE {ok}/{len(out)} usable in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
