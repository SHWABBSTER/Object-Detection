import pyrealsense2 as rs
import numpy as np
import cv2
import sys

# Initialize the parameters
confThreshold = 0.5
nmsThreshold = 0.4
inpWidth = 416
inpHeight = 416
classesFile = "coco.names"

# Configure depth and color streams
pipeline = rs.pipeline()
config = rs.config()

# Get device product line for setting a supporting resolution
pipeline_wrapper = rs.pipeline_wrapper(pipeline)
pipeline_profile = config.resolve(pipeline_wrapper)
device = pipeline_profile.get_device()
device_product_line = str(device.get_info(rs.camera_info.product_line))
depth_sensor = pipeline_profile.get_device().first_depth_sensor()
depth_scale = depth_sensor.get_depth_scale()
found_rgb = False

for s in device.sensors:
    if s.get_info(rs.camera_info.name) == 'RGB Camera':
        found_rgb = True
        break
if not found_rgb:
    print("The demo requires Depth camera with Color sensor")
    sys.exit()

config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

if device_product_line == 'L500':
    config.enable_stream(rs.stream.color, 960, 540, rs.format.bgr8, 30)
else:
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
# Start streaming
pipeline.start(config)

def getOutputsNames(net):
    layersNames = net.getLayerNames()
    unconnected_layers = net.getUnconnectedOutLayers()
    if isinstance(unconnected_layers, int):  # If it's a single integer, wrap it in a list
        unconnected_layers = [unconnected_layers]
    return [layersNames[idx - 1] for idx in unconnected_layers]

def process_detection(frame, outs, depth_frame):
    frameHeight = frame.shape[0]
    frameWidth = frame.shape[1]
    classIds = []
    confidences = []
    boxes = []
    for out in outs:
        for detection in out:
            scores = detection[5:]
            classId = np.argmax(scores)
            confidence = scores[classId]
            if confidence > confThreshold:
                center_x = int(detection[0]*frameWidth)
                center_y = int(detection[1]*frameHeight)
                width = int(detection[2]*frameWidth)
                height = int(detection[3]*frameHeight)
                left = int(center_x - width/2)
                top = int(center_y - height/2)
                classIds.append(classId)
                confidences.append(float(confidence))
                boxes.append([left,top,width,height])
    indices = cv2.dnn.NMSBoxes(boxes, confidences, confThreshold, nmsThreshold)
    if isinstance(indices, np.ndarray):
        indices = indices.tolist()  # Convert to list if it's an ndarray
    print("Indices:", indices)  # For debugging
    if len(indices) > 0:
        for i in indices:
            if isinstance(i, int):  # Check if i is an integer
                i = [i]  # Wrap i in a list if it's an integer
            box = boxes[i[0]]  # Access the first element of i
            left = box[0]
            top = box[1]
            width = box[2]
            height = box[3]
            x = int(left+width/2)
            y = int(top+ height/2)
            drawPredicted(classIds[i[0]], confidences[i[0]], left, top, left+width, top+height, frame, x, y, depth_frame)


# Define the drawPredicted function (placeholder)
def drawPredicted(classId, conf, left, top, right, bottom, frame, x, y, depth_frame):
    # Draw bounding box
    cv2.rectangle(frame, (left, top), (right, bottom), (255, 178, 50), 3)
    
    # Draw label
    label = f'{classes[classId]}: {conf:.2f}'
    labelSize, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    top = max(top, labelSize[1])
    cv2.putText(frame, label, (left, top - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 0), 2)

    # Draw point
    cv2.circle(frame, (x, y), radius=1, color=(0, 0, 254), thickness=5)

    # Display distance
    if depth_frame is not None:
        distance = depth_frame.get_distance(x, y)
        distance_string = f"Dist: {depth_scale * distance:.2f} meter away"
        cv2.putText(frame, distance_string, (left, top + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 0), 2)

if __name__ == "__main__":
    classes = None
    with open(classesFile, "rt") as f:
        classes = f.read().rstrip('\n').split('\n')
    modelConfiguration = "yolov3.cfg"
    modelWeights = "yolov3.weights"
    net = cv2.dnn.readNetFromDarknet(modelConfiguration, modelWeights)
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    try:
        while True:
            # Wait for a coherent pair of frames: depth and color
            frames = pipeline.wait_for_frames()
            depth_frame = frames.get_depth_frame()
            color_frame = frames.get_color_frame()
            if not depth_frame or not color_frame:
                continue
            # Convert images to numpy arrays
            depth_image = np.asanyarray(depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())
            blob = cv2.dnn.blobFromImage(color_image, 1/255, (inpWidth, inpHeight), [0,0,0],1,crop=False)
            net.setInput(blob)
            outs = net.forward(getOutputsNames(net))
            # Apply colormap on depth image (image must be converted to 8-bit per pixel first)
            depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET)
            process_detection(color_image, outs, depth_frame)  # Pass depth_frame here
            depth_colormap_dim = depth_colormap.shape
            color_colormap_dim = color_image.shape
            # If depth and color resolutions are different, resize color image to match depth image for display
            if depth_colormap_dim != color_colormap_dim:
                resized_color_image = cv2.resize(color_image, dsize=(depth_colormap_dim[1], depth_colormap_dim[0]),
                                                 interpolation=cv2.INTER_AREA)
                images = np.hstack((resized_color_image, depth_colormap))
            else:
                images = np.hstack((color_image, depth_colormap))
            # Show images
            cv2.imshow('Yolo in RealSense made by Tony', images)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        # Stop streaming
        pipeline.stop()

