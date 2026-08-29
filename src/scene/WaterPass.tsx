// The scene pass the water surface reads from.
//
// UE's single-layer water composites against the scene BEHIND the water, which
// means it needs that scene's colour and, crucially, its DEPTH — the length of
// the water column along each view ray is the whole difference between "sea"
// and "slab" (see waterMaterial.ts). Nothing in a normal three.js transparent
// draw provides that, so the frame is rendered twice:
//
//   1. every object EXCEPT the water surfaces, into an offscreen target that
//      carries a DepthTexture;
//   2. the real frame, with the water surfaces now able to sample both.
//
// Taking a useFrame priority above 0 turns OFF react-three-fiber's automatic
// render, so this component owns the frame from here on and must issue both
// draws itself.
//
// The pre-pass target is LINEAR (no colour-space conversion on a render
// target), which is the right space to composite in; the water shader does its
// own sRGB conversion on the way out to the canvas.
import { useEffect, useMemo } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

/** Objects carrying this in userData are excluded from the pre-pass. */
export const WATER_SURFACE_FLAG = "isWaterSurface";

export function WaterPass({ material }: { material: THREE.ShaderMaterial | null }) {
  const { gl, scene, camera, size } = useThree();

  const target = useMemo(() => {
    const t = new THREE.WebGLRenderTarget(1, 1, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      type: THREE.HalfFloatType,
    });
    const d = new THREE.DepthTexture(1, 1);
    d.type = THREE.UnsignedIntType;
    d.format = THREE.DepthFormat;
    t.depthTexture = d;
    return t;
  }, []);

  useEffect(() => () => target.dispose(), [target]);

  useFrame(() => {
    if (!material) {
      gl.render(scene, camera);
      return;
    }
    const dpr = gl.getPixelRatio();
    const w = Math.max(1, Math.floor(size.width * dpr));
    const h = Math.max(1, Math.floor(size.height * dpr));
    if (target.width !== w || target.height !== h) target.setSize(w, h);

    // ---- pass 1: the world without the water --------------------------------
    const hidden: THREE.Object3D[] = [];
    scene.traverse((o) => {
      if (o.userData?.[WATER_SURFACE_FLAG] && o.visible) {
        o.visible = false;
        hidden.push(o);
      }
    });
    const prevTarget = gl.getRenderTarget();
    gl.setRenderTarget(target);
    gl.clear();
    gl.render(scene, camera);
    gl.setRenderTarget(prevTarget);
    for (const o of hidden) o.visible = true;

    // ---- feed the water shader ----------------------------------------------
    const u = material.uniforms;
    u.tSceneColor.value = target.texture;
    u.tSceneDepth.value = target.depthTexture;
    (u.uResolution.value as THREE.Vector2).set(w, h);
    const cam = camera as THREE.PerspectiveCamera;
    u.uCameraNear.value = cam.near;
    u.uCameraFar.value = cam.far;

    // ---- pass 2: the real frame ---------------------------------------------
    gl.render(scene, camera);
  }, 1);

  return null;
}

