from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from scipy import misc
import sys
import os
import argparse
import tensorflow as tf
import numpy as np
from evaluation.lfw.util import detect_face
import cv2
from evaluation.lfw.simulatedMaskLFW import AlignDlib

dl = AlignDlib('shape_predictor_68_face_landmarks.dat')


def to_rgb(img):
    w, h = img.shape
    ret = np.empty((w, h, 3), dtype=np.uint8)
    ret[:, :, 0] = ret[:, :, 1] = ret[:, :, 2] = img
    return ret


def IOU(Reframe,GTframe):
  x1 = Reframe[0];
  y1 = Reframe[1];
  width1 = Reframe[2]-Reframe[0];
  height1 = Reframe[3]-Reframe[1];

  x2 = GTframe[0]
  y2 = GTframe[1]
  width2 = GTframe[2]-GTframe[0]
  height2 = GTframe[3]-GTframe[1]

  endx = max(x1+width1,x2+width2)
  startx = min(x1,x2)
  width = width1+width2-(endx-startx)

  endy = max(y1+height1,y2+height2)
  starty = min(y1,y2)
  height = height1+height2-(endy-starty)

  if width <=0 or height <= 0:
    ratio = 0
  else:
    Area = width*height
    Area1 = width1*height1
    Area2 = width2*height2
    ratio = Area*1./(Area1+Area2-Area)
  return ratio


def main(args):
    #facenet.store_revision_info(src_path, output_dir, ' '.join(sys.argv))
    dataset = face_image.get_dataset('lfw', args.input_dir)
    print('dataset size', 'lfw', len(dataset))
    
    print('Creating networks and loading parameters')
    
    with tf.Graph().as_default():
        #gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=args.gpu_memory_fraction)
        #sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options, log_device_placement=False))
        sess = tf.Session()
        with sess.as_default():
            pnet, rnet, onet = detect_face.create_mtcnn(sess, None)
    
    minsize = 20
    threshold = [0.6,0.7,0.9]
    factor = 0.85

    # Add a random key to the filename to allow alignment using multiple processes
    #random_key = np.random.randint(0, high=99999)
    #bounding_boxes_filename = os.path.join(output_dir, 'bounding_boxes_%05d.txt' % random_key)
    #output_filename = os.path.join(output_dir, 'faceinsight_align_%s.lst' % args.name)

    if not os.path.exists(args.output_dir):
      os.makedirs(args.output_dir)

    output_filename = os.path.join(args.output_dir_mask, 'lst.txt')
    mask_ftx=open( os.path.join(args.output_dir_mask, 'mask.txt'),'w')
    masklog=open( os.path.join(args.output_dir_mask, 'lfw-log.txt'),'w')

    
    with open(output_filename, "w") as text_file:
        nrof_images_total = 0
        nrof = np.zeros( (5,), dtype=np.int32)
        for fimage in dataset:
            if nrof_images_total%100==0:
              print("Processing %d, (%s)" % (nrof_images_total, nrof))
            nrof_images_total += 1
            #if nrof_images_total<950000:
            #  continue
            image_path = fimage.image_path
            if not os.path.exists(image_path):
              print('image not found (%s)'%image_path)
              continue
            filename = os.path.splitext(os.path.split(image_path)[1])[0]
            #print(image_path)
            try:
                img = misc.imread(image_path)
            except (IOError, ValueError, IndexError) as e:
                errorMessage = '{}: {}'.format(image_path, e)
                print(errorMessage)
            else:
                if img.ndim<2:
                    print('Unable to align "%s", img dim error' % image_path)
                    #text_file.write('%s\n' % (output_filename))
                    continue
                if img.ndim == 2:
                    img = to_rgb(img)
                img = img[:,:,0:3]
                _paths = fimage.image_path.split('/')
                a,b = _paths[-2], _paths[-1]
                target_dir = os.path.join(args.output_dir, a)
                if not os.path.exists(target_dir):
                  os.makedirs(target_dir)
                target_file = os.path.join(target_dir, b)
                _minsize = minsize
                _bbox = None
                _landmark = None
                bounding_boxes, points = detect_face.detect_face(img, _minsize, pnet, rnet, onet, threshold, factor)
                nrof_faces = bounding_boxes.shape[0]
                if nrof_faces>0:
                  det = bounding_boxes[:,0:4]
                  img_size = np.asarray(img.shape)[0:2]
                  bindex = 0
                  if nrof_faces>1:
                      bounding_box_size = (det[:,2]-det[:,0])*(det[:,3]-det[:,1])
                      img_center = img_size / 2
                      offsets = np.vstack([ (det[:,0]+det[:,2])/2-img_center[1], (det[:,1]+det[:,3])/2-img_center[0] ])
                      offset_dist_squared = np.sum(np.power(offsets,2.0),0)
                      bindex = np.argmax(bounding_box_size-offset_dist_squared*2.0) # some extra weight on the centering
                  _bbox = bounding_boxes[bindex, 0:4]
                  _landmark = points[:, bindex].reshape( (2,5) ).T
                  nrof[0]+=1
                else:
                  nrof[1]+=1

                warped = face_preprocess.preprocess(img, bbox=_bbox, landmark = _landmark, image_size=args.image_size)
                bgr = warped[...,::-1]
                #print(bgr.shape)
                cv2.imwrite(target_file, bgr)
                oline = '%d\t%s\t%d\n' % (1,target_file, int(fimage.classname))
                text_file.write(oline)
                target_dir = os.path.join(args.output_dir_mask ,  a)
                if not os.path.exists(target_dir):
                        os.makedirs(target_dir)
                target_file = os.path.join(target_dir, b)
                if (_bbox is None):
                    print(target_file)

                mask_image,mask_type,mask_color = dl.simulateMask(img,boundingbox=_bbox)
                if not (mask_image is None):
                        warped = face_preprocess.preprocess(mask_image, bbox=_bbox, landmark=_landmark, image_size=args.image_size)
                        bgr = warped[..., ::-1]
                        # print(bgr.shape)
                        cv2.imwrite(target_file, bgr)
                        masklog.write(target_file+ " "+ str(mask_type)+ " "+ str(mask_color[0])+ " "+ str(mask_color[1])+ " "+ str(mask_color[2])+"\n")
                else:
                        mask_ftx.write('%d\t%s\t%d\n' % (1,target_file, int(fimage.classname)))
                        print(target_file+ " "+ str(mask_type)+ " "+ str(mask_color[0])+ " "+ str(mask_color[1])+ " "+ str(mask_color[2])+"\n")




def parse_arguments(argv):
    parser = argparse.ArgumentParser()
    
    parser.add_argument('--input-dir', type=str, default='Data/lfw' , help='Directory with unaligned images.')
    parser.add_argument('--output-dir', type=str,default='Data/lfw_aligned', help='Directory with aligned face thumbnails.')
    parser.add_argument('--output-dir-mask', type=str,default='Data/lfw_aligned_mask_random', help='Directory with aligned face thumbnails.')

    parser.add_argument('--image-size', type=str, help='Image size (height, width) in pixels.', default='112,112')
    #parser.add_argument('--margin', type=int,
    #    help='Margin for the crop around the bounding box (height, width) in pixels.', default=44)
    return parser.parse_args(argv)

if __name__ == '__main__':
    main(parse_arguments(sys.argv[1:]))


