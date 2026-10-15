public class Main {
    public static void main(String[] args) {
        IntLinkedList list = new IntLinkedList();
        list.add(3);
        list.add(5);
        list.add(7);
        System.out.println("before: " + list + " size=" + list.size());
        System.out.println("remove(5) -> " + list.remove(5));
        System.out.println("after:  " + list + " size=" + list.size());
    }
}
