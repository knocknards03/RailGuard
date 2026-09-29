# DataFlair Abandoned Object Detection
import numpy as np
import cv2
from tracker import *

# Initialize Tracker
tracker = ObjectTracker()


# location of first frame
firstframe_path =r'Frame.png'

firstframe = cv2.imread(firstframe_path)
firstframe_gray = cv2.cvtColor(firstframe, cv2.COLOR_BGR2GRAY)
firstframe_blur = cv2.GaussianBlur(firstframe_gray,(3,3),0)
# cv2.imshow("First frame", firstframe_blur)

# location of video
file_path ='cut.mp4'
cap = cv2.VideoCapture(file_path)

while (cap.isOpened()):
    ret, frame = cap.read()
    
    frame_height, frame_width, _ = frame.shape

    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame_blur = cv2.GaussianBlur(frame_gray,(3,3),0)

    # find diffrence between first frame and current frame
    frame_diff = cv2.absdiff(firstframe_blur, frame_blur)
    # cv2.imshow("frame diff",frame_diff)

    #Canny Edge Detection
    edged = cv2.Canny(frame_diff,5,200) 
    # cv2.imshow('CannyEdgeDet',edged)

    kernel = np.ones((10,10),np.uint8) #higher the kernel, eg (20,20), more will be eroded or dilated
    thresh = cv2.morphologyEx(edged,cv2.MORPH_CLOSE, kernel, iterations=2)

    # cv2.imshow('Morph_Close', thresh)

    # find contours of all detected objects
    cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)

    detections=[]
    count = 0
    for c in cnts:
        contourArea = cv2.contourArea(c)
        
        if contourArea > 50 and contourArea < 10000:
            count +=1

            (x, y, w, h) = cv2.boundingRect(c)

            detections.append([x, y, w, h])

    _, abandoned_objects = tracker.update(detections)
    
    # print(abandoned_objects)
    
    # Draw rectangle and id over all abandoned objects
    for objects in abandoned_objects:
        _, x2, y2, w2, h2, _ = objects

        
        cv2.putText(frame, "Suspicious object detected", (x2, y2 - 10), cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 0, 255), 2)
        cv2.rectangle(frame, (x2, y2), (x2 + w2, y2 + h2), (0, 0, 255), 2)


    cv2.imshow('main',frame)
    if cv2.waitKey(15) == ord('q'):
        break

cv2.destroyAllWindows()