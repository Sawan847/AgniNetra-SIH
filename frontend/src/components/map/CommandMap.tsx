import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  FIRE_CLASS_COLORS,
  type Hotspot,
  type IndustrialFacility,
} from "../../types";

export interface CommandMapProps {
  hotspots: Hotspot[];
  facilities?: IndustrialFacility[];
  selectedHotspot?: Hotspot | null;
  onSelectHotspot?: (hotspot: Hotspot) => void;
  showHeatmap?: boolean;
  showFacilities?: boolean;
  showClusters?: boolean;
}

export function CommandMap({
  hotspots,
  facilities: _facilities = [],
  selectedHotspot,
  onSelectHotspot,
  showHeatmap = false,
  showFacilities: _showFacilities = true,
  showClusters = false,
}: CommandMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [coords, setCoords] = useState<{ lng: number; lat: number; zoom: number }>({
    lng: 78.96,
    lat: 20.59,
    zoom: 4.5,
  });

  // Initialize MapLibre
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    try {
      const map = new maplibregl.Map({
        container: containerRef.current,
        style: {
          version: 8,
          sources: {
            carto: {
              type: "raster",
              tiles: [
                "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
                "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
              ],
              tileSize: 256,
              attribution:
                '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
            },
          },
          layers: [
            {
              id: "carto-tiles",
              type: "raster",
              source: "carto",
              minzoom: 0,
              maxzoom: 19,
            },
          ],
        },
        center: [78.96, 20.59],
        zoom: 4.8,
      });

      map.addControl(new maplibregl.NavigationControl(), "top-right");
      map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");

      map.on("mousemove", (e) => {
        setCoords({
          lng: Number(e.lngLat.lng.toFixed(3)),
          lat: Number(e.lngLat.lat.toFixed(3)),
          zoom: Number(map.getZoom().toFixed(1)),
        });
      });

      mapRef.current = map;
    } catch (err) {
      console.warn("MapLibre initialization fallback:", err);
    }

    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // Update GeoJSON Hotspots layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const geojsonData: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: hotspots.map((h) => ({
        type: "Feature",
        id: h.id,
        geometry: {
          type: "Point",
          coordinates: [h.longitude, h.latitude],
        },
        properties: {
          id: h.id,
          frp: h.frp ?? 10,
          brightness: h.brightness ?? 320,
          predicted_class: h.predicted_class || "uncertain",
          satellite: h.satellite || "VIIRS",
          acq_date: h.acq_date || "Recent",
        },
      })),
    };

    const updateLayers = () => {
      if (!map.isStyleLoaded()) {
        map.once("style.load", updateLayers);
        return;
      }

      // Hotspots Source
      const source = map.getSource("hotspots-source") as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(geojsonData);
      } else {
        map.addSource("hotspots-source", {
          type: "geojson",
          data: geojsonData,
          cluster: showClusters,
          clusterMaxZoom: 14,
          clusterRadius: 50,
        });

        // Heatmap layer
        map.addLayer({
          id: "hotspots-heat",
          type: "heatmap",
          source: "hotspots-source",
          maxzoom: 12,
          paint: {
            "heatmap-weight": ["interpolate", ["linear"], ["get", "frp"], 0, 0.2, 300, 1],
            "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 1, 12, 3],
            "heatmap-color": [
              "interpolate",
              ["linear"],
              ["heatmap-density"],
              0,
              "rgba(33, 102, 172, 0)",
              0.2,
              "rgb(103, 169, 207)",
              0.4,
              "rgb(209, 229, 240)",
              0.6,
              "rgb(253, 219, 199)",
              0.8,
              "rgb(239, 138, 98)",
              1,
              "rgb(178, 24, 43)",
            ],
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 4, 12, 28],
            "heatmap-opacity": showHeatmap ? 0.85 : 0,
          },
        });

        // Circle points
        map.addLayer({
          id: "hotspots-points",
          type: "circle",
          source: "hotspots-source",
          paint: {
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              3,
              5,
              8,
              8,
              12,
              12,
            ],
            "circle-color": [
              "match",
              ["get", "predicted_class"],
              "accidental_industrial_fire",
              FIRE_CLASS_COLORS.accidental_industrial_fire,
              "persistent_industrial_source",
              FIRE_CLASS_COLORS.persistent_industrial_source,
              "forest_or_natural_fire",
              FIRE_CLASS_COLORS.forest_or_natural_fire,
              "agricultural_burning",
              FIRE_CLASS_COLORS.agricultural_burning,
              "mining_or_other",
              FIRE_CLASS_COLORS.mining_or_other,
              FIRE_CLASS_COLORS.uncertain,
            ],
            "circle-stroke-width": 2,
            "circle-stroke-color": "#FFFFFF",
            "circle-opacity": showHeatmap ? 0.4 : 0.95,
          },
        });

        map.on("click", "hotspots-points", (e) => {
          const feature = e.features?.[0];
          if (!feature?.properties) return;
          const matched = hotspots.find((h) => h.id === feature.properties?.id);
          if (matched && onSelectHotspot) {
            onSelectHotspot(matched);
          }
        });

        map.on("mouseenter", "hotspots-points", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "hotspots-points", () => {
          map.getCanvas().style.cursor = "";
        });
      }

      // Update heatmap visibility
      if (map.getLayer("hotspots-heat")) {
        map.setPaintProperty("hotspots-heat", "heatmap-opacity", showHeatmap ? 0.85 : 0);
      }
    };

    updateLayers();
  }, [hotspots, showHeatmap, showClusters, onSelectHotspot]);

  // Center on selected hotspot if changed
  useEffect(() => {
    if (!mapRef.current || !selectedHotspot) return;
    mapRef.current.flyTo({
      center: [selectedHotspot.longitude, selectedHotspot.latitude],
      zoom: Math.max(mapRef.current.getZoom(), 8),
      speed: 1.2,
    });
  }, [selectedHotspot]);

  return (
    <div className="map-canvas-container" style={{ minHeight: "450px" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%", position: "absolute" }} />

      {/* Coordinate & Zoom HUD */}
      <div className="map-hud">
        <span style={{ color: "var(--primary)" }}>📍</span>
        <span>
          LAT: {coords.lat}°N &nbsp;•&nbsp; LON: {coords.lng}°E &nbsp;•&nbsp; ZOOM: {coords.zoom}x
        </span>
        <span className="badge badge--info" style={{ marginLeft: "auto" }}>
          {hotspots.length} Active Detections
        </span>
      </div>
    </div>
  );
}
