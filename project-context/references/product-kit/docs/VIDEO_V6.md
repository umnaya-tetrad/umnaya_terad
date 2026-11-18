# Video v6 — explicit navigation and photo capture

Composition SmartNotebookV6. Duration 135 seconds (4050 frames at 30fps), 1920×1080. Earlier versions are preserved. White background, larger phone, touch indicators and 1.6-second zoom in remain.

Teacher confirmation now includes a touch on «Вернуться к отчёту» at 59.2 seconds. The report appears at 60 seconds and holds in overview, then zooms to «Частые ошибки». A touch on that button at 64.2 seconds precedes analytics at 66 seconds. Previously confirmation jumped directly to analytics with no touch.

Student capture is explicit: home 77–83, camera 83–89, photo review 89–96, processing 96–99, error/hint 99–109, correction/retry 109–115, camera again 115–118, new-photo review 118–124, correct result 124–130. Closing invitation: 130–135.

Camera includes framing guide, shutter control, frame-driven touch pulse, shutter flash and captured status. First shutter press: 87.2 seconds; second: 117.2 seconds. Camera illustration and review use the same mathematical example; actual handwritten photos remain deferred as agreed. Optional AppScreen cameraCapture prop updates the retry/retake wording in v6 while keeping existing prototypes and earlier videos unchanged.

Files: src/scenes/video-v6/ActionVideo.tsx, CameraCapture.tsx, action.css. Export: npm run render:video → out/smart-notebook-v6.mp4. Frames: npm run build:offline (HTML-макеты); сценарий экспорта контрольных кадров остался в исходном видеопроекте. Studio: адрес Studio из npm run studio, композиция SmartNotebookV6.

Validation: ESLint/TypeScript, production bundle, smoke render and smoke still passed. Rendered frames reviewed for report navigation, camera shutter and photo-review continuity. Silent for live commentary; no venue/projector hardware test.

Final export: 4050/4050 frames encoded, 29.3 MB, 135 seconds, H.264 Full HD at 30fps. Browser playback verified: readyState 4, playing, 1920×1080, no media error. Metadata: out/video/metadata-v6.json. Render log: docs/evidence/video-v6-render.log. Keyframe 1780 confirms the return touch is on «Вернуться к отчёту»; 1928 confirms the analytics touch is on «Частые ошибки».


Примечание упаковки 18 ноября: пути out/video/v6-frames, metadata-v6.json и старые журналы в тексте выше относятся к первичной проверке исходного видеопроекта. Они не включены в этот комплект. Готовый файл перенесён в media/smart-notebook-v6.mp4; текущие проверки комплекта см. STATUS.md.
