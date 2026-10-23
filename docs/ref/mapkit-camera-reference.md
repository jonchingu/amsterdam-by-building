# How Apple MapKit coordinates camera and zoom, and how the Toranomon viewer follows it

Reference for the camera in `tokyo-lod3-survey.html` ("Toranomon in 3D"). Apple API facts are from Apple's MapKit and
SwiftUI documentation, read 2026-10-15; links at the end.

## 1. MapKit's model: the camera is described from the ground, not from the eye

MapKit never asks you for an eye position. A camera (`MKMapCamera`, or `MapCamera` in SwiftUI) is four numbers anchored
on the map:

| Property | Meaning (Apple's wording, abridged) |
|---|---|
| `centerCoordinate` | The map coordinate at the center of the map view. |
| `centerCoordinateDistance` | The distance from the center point of the map to the camera, in meters. |
| `heading` | The heading of the camera, in degrees, relative to true north. |
| `pitch` | The viewing angle of the camera, in degrees, relative to the map perpendicular. 0 looks straight down. |
| `altitude` | The altitude above the ground, in meters. Derived from distance and pitch; kept for older code. |

`MKMapCamera(lookingAtCenter:fromDistance:pitch:heading:)` builds one from exactly these values.
`MKMapCamera(lookingAtCenter:fromEyeCoordinate:eyeAltitude:)` is the only eye-first form, and MapKit converts it back:
"the initializer calculates the required pitch and heading angles to accommodate the specified eye position and altitude."

**Zoom is distance.** Zooming changes only `centerCoordinateDistance`. The center, heading and pitch stay as they are,
so the same spot stays in the middle and the angle doesn't jump. Zoom level, visible region and altitude all follow
from distance plus pitch. When you assign a camera, MapKit "takes the camera's pitch and altitude into account when
calculating the visible region".

## 2. Constraints are on the same terms

| API | What it limits |
|---|---|
| `MKMapView.CameraZoomRange(minCenterCoordinateDistance:maxCenterCoordinateDistance:)` (iOS 13+) | How close and how far the camera can get, as center distance in meters. Apple: "a camera zoom range that limits the distances to which the user can zoom." |
| `MKMapView.CameraBoundary(coordinateRegion:)` / `(mapRect:)` (iOS 13+) | "A boundary of an area within which the map's center needs to remain." It limits the **center**, not the eye. |
| `MapCameraBounds(centerCoordinateBounds:minimumDistance:maximumDistance:)` (SwiftUI, iOS 17+) | Both of the above in one value. |
| `isZoomEnabled`, `isScrollEnabled`, `isRotateEnabled`, `isPitchEnabled` | Turn single gesture families on or off. |

Because the boundary limits the center and the zoom range limits distance, the two never fight: you can always zoom out
to the maximum while the center stays in bounds.

## 3. Animated moves and who wins

- `setCamera(_:animated:)` moves to a new camera with MapKit's own interpolation.
- SwiftUI's `mapCameraKeyframeAnimator(trigger:keyframes:)` (iOS 17+) runs keyframes over `MapCamera` values: center,
  distance, heading and pitch, each on its own track. Apple: "If the user performs a gesture while the animation is in
  progress, the animation will be immediately removed, allowing the interaction to take control of the camera."
  Animation is a suggestion; the person's gesture always wins.

## 4. Gestures, as people know them from Apple Maps

These are Apple Maps behaviours as commonly described, not documented API contracts.

- **Pinch** zooms about the point between the fingers; **double-tap** zooms in there; **two-finger tap** zooms out.
  Zoom anchors on the touched point, not on the screen center.
- **Two-finger rotate** changes heading. **Two-finger vertical drag** changes pitch.
- **Pitch narrows as you zoom out.** A zoomed-out map flattens toward 0°, so tilting can't show the horizon over a
  whole city.

## 5. What the viewer does with this (PR "MapKit-style camera and drone controls")

| MapKit idea | Viewer |
|---|---|
| Camera = center, distance, heading, pitch | `getCam()` / `setCam()` read and write `{center, distance, heading, pitch}`. Presets are defined this way (e.g. towers: distance 540 m, heading 328°, pitch 66°). The readout under the view shows all of them, including the center as lat/lon. |
| `CameraZoomRange` | `ZOOM_RANGE = {min: 40, max: 2500}` m, enforced on every move. |
| `CameraBoundary` | `BOUNDARY` keeps the **center** within 35.6615–35.6715 N, 139.7440–139.7610 E (the tiles plus a margin). `CENTRE_CEILING` keeps it between the street and 300 m up, just over the 265 m towers. |
| Pitch narrows with distance | `maxPitch(distance)`: 78° up to 300 m, easing on a log scale to 40° at 2,500 m. |
| Zoom about the gesture point | Wheel and double-click scale the eye and the center about the ground point under the pointer, so that point stays put. Pinch still uses three.js OrbitControls' dolly toward the center (r147 has no zoom-to-cursor). |
| `setCamera(animated:)` / keyframes | `flyTo()`: center, heading (shortest way round), pitch and distance ease together. Distance adds a lift of up to 900 m on long hops, so the camera rises and comes back down like a drone transit. With the system's reduce-motion setting on, the buttons cut straight to the view instead. |
| Gesture removes the animation | Any pointer down, wheel, drag start or drone key stops a flight or an orbit. A preset button stays lit until the person actually moves the camera. |

### Drone controls (beyond MapKit)

MapKit has no free-flight mode. The viewer adds one that still keeps the MapKit constraints:

- **Keys** (after clicking the view): `W`/`S` or ↑/↓ fly forward and back along the heading, `A`/`D` slide sideways,
  `Q`/`E` or ←/→ turn, `R`/`F` climb and descend, `Shift` triples speed. The pad in the view's corner does the same on
  touch screens. Keys pressed with Ctrl, Cmd or Alt are left to the browser (Ctrl+F still finds, nothing descends), and
  pressing one of those modifiers lets go of any held drone key, since macOS sends no key-up for a letter released while
  Cmd is down.
- **Inertia:** each input sets a target velocity, and the camera eases toward it (time constant about 0.2 s). Starts and
  stops are smooth, not instant.
- **Speed follows height:** 0.8 × the height above the street per second, clamped to 12–450 m/s. Low passes are slow
  and high transits are fast, as with zoom-dependent pan speed in map apps.
- **Turning** swings the center around the eye: the drone yaws in place instead of orbiting the target.
- **Climbing** lifts the center with the eye until the center reaches the 300 m ceiling. After that only the eye rises,
  tilting down toward the center, and the climb ends straight overhead at the 2,500 m zoom limit. Without the ceiling the
  center rose with the eye, so the zoom range never applied: 15 s of `R` reached 6.8 km, near the far clipping plane.
- **Orbit** circles the current center at 9°/s, a standard drone shot.
- All moves still pass `constrain()`: center boundary and ceiling, zoom range, distance-dependent pitch, and the eye
  stays at least 4 m above street level.
- The scroll wheel zooms only over the 3D view itself. Over the pad or the record card it scrolls as usual.

### Route anchors: `tokyo-drone-route.html`

A second page takes the drone further: first-person flight down between the towers, a lens zoom, and a planned route
that flies itself. It is MapKit's keyframe idea with a drone's camera model in place of `MKMapCamera`.

| MapKit keyframe animator | Drone route page |
|---|---|
| `KeyframeTrack` per camera property | One anchor holds every property: position, heading, tilt, zoom, hold, cruise speed, optional aim point |
| `CubicKeyframe` (smooth through a value) | Heading, tilt and log-zoom follow Catmull–Rom curves across anchors; position follows a centripetal Catmull–Rom curve |
| `LinearKeyframe` / `SpringKeyframe` timing | Each leg's progress along the curve is a cubic Hermite in time: zero speed at holds and the ends, the mean of the two legs' speeds at anchors flown through |
| `MapCamera(centerCoordinate:distance:…)` | `MapCamera` looks *at* a centre; an anchor looks *from* a point. An aim point turns it back into a look-at, and two anchors aimed at the same point make a tracking shot |
| The animation stops when the person interacts | Same: any key, drag, wheel or pinch pauses playback and leaves the drone where it is; Play blends back onto the route over 0.7 to 2.5 s |

- **Zoom is the lens, not distance.** In flight, zoom changes the field of view (62° at 1× to about 5° at 12×), as on a
  drone's camera. Getting closer means flying closer. Look-around speed scales with the field of view, so a long lens
  stays steady.
- **Walls.** As each tile loads, its triangles are drawn into a 2 m height grid (the tallest surface over each cell).
  The drone, a 2.5 m disc, can't go below the grid's height plus 1.2 m. At a wall it slides along the face, using
  a normal estimated from the blocked directions around it. The same grid flags route legs that pass through a
  building (drawn red), feeds the "wall N m" readout and shades the map. Flying under overhangs isn't possible.
- **Speed in the streets.** 0.45 × the height above the street per second, clamped to 8–90 m/s, so street-level flight
  is slow enough to steer.
- **The sample route** (95 s, 9 anchors) was planned on that grid. It comes in from Shimbashi, drops to 40 m and passes
  the 40 m gap between Mori Tower and Business Tower (its closest wall is 15 m away), climbs the face of Station Tower,
  then arcs round Mori Tower's crown while the lens closes from 1.6× to 3.2×.

## Sources

- MKMapCamera: https://developer.apple.com/documentation/mapkit/mkmapcamera
- MKMapView.CameraZoomRange: https://developer.apple.com/documentation/mapkit/mkmapview/camerazoomrange-swift.class
- MKMapView.CameraBoundary: https://developer.apple.com/documentation/mapkit/mkmapview/cameraboundary-swift.class
- MapCameraBounds: https://developer.apple.com/documentation/mapkit/mapcamerabounds
- mapCameraKeyframeAnimator(trigger:keyframes:): https://developer.apple.com/documentation/swiftui/view/mapcamerakeyframeanimator(trigger:keyframes:)
- MapKit JS CameraZoomRange (same model on the web): https://developer.apple.com/documentation/mapkitjs/camerazoomrange
